

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

