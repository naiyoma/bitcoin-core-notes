### Deterministic Per-Requestor Timestamp Distortion

We want to change (distort) timestamps so that:

1. Each requestor sees slightly different timestamps this breaks correlation
2. Old addresses keep aging toward `IsTerrible()` so no zombie persistence
3. The distortion cannot be reversed by querying multiple times no defuzzing

---

## Why Not Simple Fuzzing?

With fuzzing, each request gets a new random noise value:

Theres the risk that an attacker could query multiple times and try 
and defuzz this timestamps (given that they know the fuzzing window )



How can be add some noise and make it hard/impossible to defuzz

## The Formula

```
1. h      = H(addr, peer, secret)
2. range  = 3d + (h % 2d)          ->  range ∈ [3d, 5d]
3. window = range + 1d
4. Δ      = (h % window) - range   ->  Δ ∈ [-range, +1d]
5. t'     = real_timestamp + Δ
6. t_final = floor(t' / BUCKET) * BUCKET
```

---

## Step by Step

### Step 1  Source of controlled randomness

```
h = H(addr, peer, secret)
```

We hash three things together: the address, the requestor's network identity,
and a node-local secret. This produces a large integer.

```
H("xyz.onion", "ipv4_key", secret) = 84729301847562901
H("xyz.onion", "tor_key",  secret) = 31047829104756234
H("abc.onion", "ipv4_key", secret) = 59103847291047832
```

Properties:
- Same inputs -> same output always (deterministic)
- Different inputs -> completely different output
- Cannot be reversed without the secret

---

### Step 2 Pick a shift size

```
range = 3d + (h % 2d)   ->   range ∈ [3d, 5d]
```

We want the shift to be somewhere between 3 and 5 days. `h % 2d` gives a
value between 0 and 2 days, so adding 3 days gives us our range.

```
84729301847562901 % 2 = 1  ->  range = 3 + 1 = 4 days
31047829104756234 % 2 = 0  ->  range = 3 + 0 = 3 days
59103847291047832 % 2 = 0  ->  range = 3 + 0 = 3 days
```

Why 3 to 5 days? 1 day is too small (attacker can still match with wide
tolerance). 7 days risks pushing addresses too far from their real age.
3 to 5 days is a reasonable balance to me .

---

### Step 3  Define the shift window

```
window = range + 1d
```

If range = 4 days then window = 5 days.

This defines the total space of possible shifts: `[-4d, +1d]`.

- Negative side: up to 4 days back (address appears older)
- Positive side: at most 1 day forward (address appears slightly fresher)

The positive side is deliberately small. If we allowed +4 days forward, a
26-day-old address could appear 22 days old — gaining 4 more days of life
before `IsTerrible()`. With only +1 day forward the maximum freshening is
minimal.

for example 

Real age = 6 days old

Negative side (-4 days back):
  The address appears to have been last seen 4 days MORE in the past
  6 days + 4 days = 10 days old  <- appears OLDER

Positive side (+1 day forward):
  The address appears to have been last seen 1 day MORE recently
  6 days - 1 day = 5 days old  <- appears FRESHER

---

### Step 4 — Compute the actual shift Δ

```
Δ = (h % window) - range   ->   Δ ∈ [-range, +1d]
```

`h % window` gives a number between 0 and window. Subtracting range centers
it so we get both negative and positive values.

Example with range = 4 days, window = 5 days = 432000 seconds:

```
h = 84729301847562901
h % 432000 = 281901 seconds = 3.26 days

Δ = 3.26 - 4.00 = -0.74 days = -17.8 hours
```

This shift is deterministic  the same address and peer always produce the
same Δ. An attacker querying many times always gets the same result and
cannot average their way to the real timestamp.

---

### Step 5 — Apply the shift

```
t' = real_timestamp + Δ
```

Example:

```
real age = 10 days
Δ       = -17.8 hours

t' = 10 days - 17.8 hours = 10.74 days
```

---

### Step 6 — Quantize to a 6-hour bucket

```
t_final = floor(t' / BUCKET) * BUCKET
```

Snap the timestamp to the nearest 6-hour mark. This removes fine-grained
precision so the attacker cannot use exact values to narrow down the real
timestamp.

```
t' = 10.74 days
10.74 days / 0.25 days = 42.96 → floor -> 42
t_final = 42 × 6h = 10.5 days
```

Values of 10.5, 10.6, 10.7, 10.74 all collapse to 10.5 — indistinguishable.

---

## Full Example

```
real age = 10 days

IPv4 peer:
  h      = H("xyz.onion", "ipv4_key", secret) = 84729301847562901
  range  = 4 days
  window = 5 days
  Δ      = -17.8 hours
  t'     = 10.74 days
  t_final = 10.5 days

Tor peer:
  h      = H("xyz.onion", "tor_key", secret) = 31047829104756234
  range  = 3 days
  window = 4 days
  Δ      = +18.2 hours
  t'     = 9.24 days
  t_final = 9.25 days

IPv4 peer sees:  10.5 days
Tor  peer sees:   9.25 days
Real age:        10.0 days  ← neither peer can recover this
```

---
