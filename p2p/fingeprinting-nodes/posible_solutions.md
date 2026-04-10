# Mitigating GETADDR Fingerprinting of Dual-Homed Nodes

## Overview

Bitcoin nodes that are reachable over multiple networks (e.g., IPv4 and Tor) can be fingerprinted by comparing `ADDR` responses across different connections. The root cause is that timestamps (`addr.nTime`) are consistent across views, allowing attackers to correlate identities.

i have this example of data 
                               address                               | ipv4_timestamp | onion_timestamp | timestamp_diff |     ipv4_datetime      |     onion_datetime     
---------------------------------------------------------------------+----------------+-----------------+----------------+------------------------+------------------------
 103.246.186.7:8333                                                  |     1774029958 |      1774029958 |              0 | 2026-03-20 21:05:58+03 | 2026-03-20 21:05:58+03
 11.21.32.70:8333                                                    |     1775021334 |      1775021334 |              0 | 2026-04-01 08:28:54+03 | 2026-04-01 08:28:54+03
 118.99.65.145:8333                                                  |     1773282955 |      1773282955 |              0 | 2026-03-12 05:35:55+03 | 2026-03-12 05:35:55+03
 129.226.157.26:8333                                                 |     1775449117 |      1775449117 |              0 | 2026-04-06 07:18:37+03 | 2026-04-06 07:18:37+03
 [2001:4958:364f:c801:1ed:f5e:a468:69b1]:8333                        |     1773731545 |      1773731545 |              0 | 2026-03-17 10:12:25+03 | 2026-03-17 10:12:25+03
 [2600:1700:41e0:1b10:f06b:5086:f4fb:d65f]:8333                      |     1775124800 |      1775124800 |              0 | 2026-04-02 13:13:20+03 | 2026-04-02 13:13:20+03
 [2a02:c206:2228:4487::1]:8333                                       |     1774162312 |      1774162312 |              0 | 2026-03-22 09:51:52+03 | 2026-03-22 09:51:52+03
 62.43.129.42:8333                                                   |     1775075979 |      1775075979 |              0 | 2026-04-01 23:39:39+03 | 2026-04-01 23:39:39+03
 68.183.234.102:8333                                                 |     1773913299 |      1773913299 |              0 | 2026-03-19 12:41:39+03 | 2026-03-19 12:41:39+03
 73.252.158.134:8312                                                 |     1775486758 |      1775486758 |              0 | 2026-04-06 17:45:58+03 | 2026-04-06 17:45:58+03
 75.207.86.75:8333                                                   |     1774123601 |      1774123601 |              0 | 2026-03-21 23:06:41+03 | 2026-03-21 23:06:41+03
 86.250.190.223:8333                                                 |     1774290093 |      1774290093 |              0 | 2026-03-23 21:21:33+03 | 2026-03-23 21:21:33+03
 95.216.16.111:8333                                                  |     1775466143 |      1775466143 |              0 | 2026-04-06 12:02:23+03 | 2026-04-06 12:02:23+03
 96.28.141.7:8333                                                    |     1774097228 |      1774097228 |              0 | 2026-03-21 15:47:08+03 | 2026-03-21 15:47:08+03
 h4qwe6wlgtg6owej35zqal47rtbrhwd5ezimpai25djwcm4z5qvofwad.onion:8333 |     1775131270 |      1775131270 |              0 | 2026-04-02 15:01:10+03 | 2026-04-02 15:01:10+03
 zdpykq3uihncjjeqcl5phpz6crawpcpz2kevqlxy65ogbojtn4vrkxyd.onion:8333 |     1774774964 |      1774774964 |              0 | 2026-03-29 12:02:44+03 | 2026-03-29 12:02:44+03




This are all the possible mitigations strategies and their possible trade-offs:

The solutions should satisfy the following conditions:

1. Privacy: Prevent cross-network fingerprinting
2. Correctness: Preserve addrman semantics (no corruption)
3. Liveness: Ensure stale nodes age out (no “zombies”)
4. Utility: Maintain usefulness of address timestamps

---

## Solution 1: Timestamp Postdating (PR #33498 Approach)


Update timestamps of addresses when responding to a `GETADDR`, effectively "refreshing" them.

### Issues 

- **Zombie propagation**: Old nodes may never become "terrible".
- **Chaining effect**: Postdated timestamps propagate across the network
- **Addrman pollution**: Stale nodes persist indefinitely

---

## Solution 2: Random Fuzzing (Static / Cached)

### Description

Apply random noise to timestamps when building the response cache.


### Issues / Trade-offs

- **Cache reuse problem**: Same noisy timestamps shared across peers
- **Still correlatable**: Identical responses across networks
- **No per-request entropy**
- Ineffective against attacker querying within cache window

---

i dont understand how this cause the issue to me it seems that this will solve the caching problem

## Solution 3: Random Fuzzing (Per Request)

### Description

Apply fresh random noise to timestamps for each request.

- Different responses per request
- Breaks deterministic correlation

### Issues / Trade-offs

-  **Averaging attack**: Attacker can recover real timestamps statistically
- **Unstable responses**: Same peer sees inconsistent data
- **Degrades usefulness**
- Adds noise but does not remove underlying signal

i also dont undersand how this will cause a problem
---

## Solution 4: Fixed Timestamps Across Networks

### Description

Return real timestamps for the requestor’s network, and fixed (e.g. constant) timestamps for other networks.

- Strong separation between network views
- Prevents direct cross-network correlation

### Issues / Trade-offs

- **State contamination**: Fake timestamps get stored by peers
- **Propagation of incorrect data**
- **Zombie problem persists (shifted downstream)**
- Kinda Violates addrman integrity

---

## Solution 5: Deterministic Per-Requestor Distortion

### Description

Apply a deterministic transformation to timestamps based on:

- Address
- Requestor identity (`m_network_key`)
- Node-local secret

The transformation is applied **only at response time**, not stored.

### Example

### Benefits

-  Breaks cross-network correlation
-  Stable per requestor (no averaging attack)
- Does not modify addrman
- No zombie propagation
- Maintains consistent view per peer

I feel like this will this is the same as fuzzing 
### Issues / Trade-offs

- Still leaks approximate age (range-based inference possible)
- Requires careful tuning of offset range
- Does not eliminate fingerprinting entirely (only degrades it)

---

## Solution 6: Large Timestamp Distortion

### Description

Apply large offsets (e.g., up to 10–20 days) to destroy correlation.

Strong privacy protection
Makes timestamps highly unreliable

### Issues / Trade-offs

- Breaks usefulness of timestamps
- Misleads peer selection
- Can bias addrman behavior indirectly
- Degrades network quality

---

## Solution 7: Network-Based Filtering

### Description

Only return addresses from the same network as the requestor.

### Benefits

- Eliminates cross-network correlation entirely
- Strong privacy guarantees

### Issues / Trade-offs

- Causes network partitioning
- Reduces address diversity
- Hurts bootstrapping and connectivity



## Solution 8: Timestamp Bucketing / Quantization

### Description

Round timestamps into coarse buckets (e.g., 1-day intervals).

### Benefits

- Reduces precision
- Limits fingerprinting signal

### Issues / Trade-offs

- Still correlatable within buckets
- Loses useful granularity
- Only partial mitigation

---



this is my most compleling solution so far


# +/-24hourTimestamp Distortion

This approach applies a **deterministic offset** to timestamps and then reduces precision via rounding off a selected window in a 6 hour bucket.

---

## Determinism

The transformation is deterministic in the sense that:

- Within the same cache window (~24 hours),
- The same requesting peer receives:
  - the same address list  
  - the same transformed timestamps  

i:e 

same peer + same address -> same distortion


---

## Offset Range

Given:


MAX_OFFSET = 24 hours


The distortion range becomes:


[-24h, +24h]


This means:

- A timestamp may appear up to **1 day older**
- Or up to **1 day newer**

---

## Bucketing

After applying the offset, timestamps are **rounded into fixed time buckets** (e.g., 6-hour intervals).

This:

- reduces timestamp precision  
- prevents fine-grained reconstruction (“defuzzing”)  
- removes ordering and spacing signals  

---

## Formula

1. `h = H(addr, peer, secret)`  
2. `h_mod = h % (2 * MAX_OFFSET)`  
3. `Δ = h_mod - MAX_OFFSET`  
4. `t' = old_timestamp + Δ`  
5. `t_final = round(t' / BUCKET) * BUCKET`  

---



A key question is whether this is equivalent to simple fuzzing.

For example:

- Original timestamp: 13 days  
- One view: 12 days  
- Another view: 14 days  

An attacker might attempt to:

- assume a ± offset  
- take the midpoint  
- try to correlate across views  

---

Distinction from Fuzzing

This approach differs from naive fuzzing because:

- The offset is **deterministic per (address, peer)**  
- Different addresses shift **independently**  
- Different peers see **different distortions**  

As a result:

- There is no single global offset to reverse  
- Matching becomes **ambiguous rather than exact**  

---

## Limitations

This does **not completely eliminate correlation**, but:

- reduces timestamp precision  
- breaks exact matching  
- significantly increases false positives  
- lowers attacker confidence  

---

## Parameter Considerations

Larger offsets (e.g., 48h or 72h) may:

- further reduce correlation  
- but degrade timestamp usefulness  

So there is a trade-off between:


privacy  network utility



but i have faced a challnege

SNR stands for Signal-to-Noise Ratio.
In this context:

Signal = the number of matches the attacker finds when comparing the SAME node's IPv4 and Tor responses
Noise = the number of matches the attacker finds when comparing two RANDOM UNRELATED nodes

The table:
Tolerance   True matches   False matches    SNR     Attack?
  24h            153            12.6        12.1x    YES
  48h            189            25.2         7.5x    YES
 168h            189            88.2         2.1x    MARGINAL
What SNR means:

SNR = 12.1x → same node produces 12x more matches than random → attacker can clearly identify the target
SNR = 2.1x → same node produces only 2x more matches than random → harder to distinguish from coincidence
SNR = 1.0x → same node produces same number of matches as random → attack completely fails

Simple analogy:
Imagine you're trying to find a specific person in a crowd by their height:

If the person is 2m tall and average is 1.7m → SNR is high → easy to find them
If everyone in the crowd is between 1.6m and 2.1m → SNR approaches 1 → impossible to single them out

For the attack to fail you need SNR close to 1.0 — meaning the attacker cannot distinguish "same node" from "two random nodes".
From the table, with ±24h MAX_OFFSET the SNR is still 12x — the attack works easily. You need MAX_OFFSET ≥ 10 days to bring SNR below 1.5x where the attack becomes unreliable.

NOW HOW I TELL the times form my getaddr because that will help me get the right snr

so the challenge is how do i introduce this noice in a way that an attacker will strugle or not be able to tell the difference 

and not cause a zombie issue whwre addresses are constally updated that they never actually become old 

i dont know tough  i do feel like maybe the snr issue is too out of scope 
because if all nodes have this noice introduced them and all timestamps are atered with how will th eattacker know 

my only issue with this solution is an attacker bieng able to scrate a script where each timestamp instead of looking for eaxact timestamp it lloks for 
match +or minues one day 