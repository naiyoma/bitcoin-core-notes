# Mitigating GETADDR Fingerprinting of Dual-Homed Nodes

## Overview

Bitcoin nodes that are reachable over multiple networks (e.g., IPv4 and Tor) can be fingerprinted by comparing `ADDR` responses across different connections. The root cause is that timestamps (`addr.nTime`) are consistent across views, allowing attackers to correlate identities.


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



