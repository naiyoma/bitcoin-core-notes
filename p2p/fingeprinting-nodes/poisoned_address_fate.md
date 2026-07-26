# Fate of every address whose timestamp the experiment forced

*Test node (`experiment-4-getaddr-timestamps`, 170.75.164.168). Cohort taken from
the complete `debug.log` **2026-06-26 → 07-20** (archive) plus **07-24** (live).
Fate read from one `getrawaddrman` snapshot at **2026-07-24 13:14:54Z**.
Tool: `poisoned_fate.py`.*

This follows a **named cohort** — the exact addresses the patch tampered with,
identified by their `experiment4: addr=… forced_nTime=…` log lines — rather than
inferring from population statistics. That makes every row below a count of
specific addresses, not an estimate.

---

## 1. The funnel — what happened to 177,581 poisoned addresses

| stage | count | share of previous |
|---|---:|---:|
| forced deliveries (log line instances) | 323,813 | — |
| **distinct addresses forced to `now − 30d`** | **177,581** | 1.82 deliveries each |
| never entered addrman — the forcing was a no-op | 173,656 | **97.79%** |
| &nbsp;&nbsp;…not in addrman at all | 137,619 | |
| &nbsp;&nbsp;…present via some other path | 36,037 | |
| **actually entered addrman as terrible** | **3,925** | **2.21%** |

**Why 97.79% were rejected.** Two filters in `AddSingle`, for opposite reasons:

- **Already known** (`addrman.cpp:545-559`). A 30-day-old timestamp cannot make a
  known entry staler: `if (addr.nTime <= pinfo->nTime) return false;`. Since ~95%
  of addrman is fresher than 30 days, almost every known address rejects the
  poison outright. Core refuses the overwrite *by design*.
- **New, but lost the bucket contest** (`addrman.cpp:581-601`). The `new` table is
  99.87% full, so a novel address nearly always collides, and wins only if the
  incumbent is terrible. Otherwise it is `Create()`d and `Delete()`d in the same
  call — the newcomer dies, not the incumbent.

The two cannot be separated exactly from the log: the 67,843 addresses loaded from
`peers.dat` at startup were deserialised, not `Added`, so "already known" and
"always lost" look identical. 41% of the cohort arrived in 2+ different getaddr
replies from different peers, which points at the already-known path dominating.

---

## 2. Fate of the 3,925 that entered

### As of the 2026-07-24 13:14Z snapshot

| outcome | count | share |
|---|---:|---:|
| **EVICTED** — gone from addrman | **2,674** | 68.13% |
| still in addrman, **still terrible** | **641** | 16.33% |
| still in addrman, **timestamp updated** (refreshed < 30 d) | **610** | 15.54% |
| *still in addrman, total* | *1,251* | *31.87%* |

### Mature cohorts only (poisoned ≥ 10 days ago, n = 2,658)

| outcome | count | share |
|---|---:|---:|
| **EVICTED** | **2,107** | **79.3%** |
| **RESCUED** (timestamp updated) | **540** | **20.3%** |
| still terrible | 11 | **0.4%** |

**Quote this one.** Given time, a poisoned entry does not stay terrible — it
resolves to evicted or rescued, roughly **4 : 1**. The 16.33% "still terrible"
above is a queue, not a steady state: 463 of those 641 were poisoned on the
morning of 07-24 and had not yet met a colliding insert.

Rescued entries' current age: p10 = 106 h, p50 = 249 h, p90 = 423 h — i.e. the
median rescue happened ~10 days ago, mid-July while the node was running.

---

## 3. By the day the address was poisoned

Exposure time is what drives the outcome, so the cohort is not homogeneous.

| poisoned | entered | evicted | still terrible | rescued | days exposed |
|---|---:|---:|---:|---:|---:|
| 2026-06-26 | 492 | 423 | 2 | 67 | 28 |
| 2026-06-27 | 136 | 108 | 0 | 28 | 27 |
| 2026-06-28 | 348 | 269 | 1 | 78 | 26 |
| 2026-06-29 | 241 | 180 | 0 | 61 | 25 |
| 2026-06-30 | 40 | 27 | 0 | 13 | 24 |
| 2026-07-01 | 152 | 124 | 1 | 27 | 23 |
| 2026-07-02 | 448 | 376 | 2 | 70 | 22 |
| 2026-07-03 | 193 | 135 | 0 | 58 | 21 |
| 2026-07-04 | 80 | 63 | 0 | 17 | 20 |
| 2026-07-05 | 81 | 58 | 0 | 23 | 19 |
| 2026-07-06 | 148 | 112 | 1 | 35 | 18 |
| 2026-07-07 | 48 | 35 | 0 | 13 | 17 |
| 2026-07-08 | 23 | 19 | 0 | 4 | 16 |
| 2026-07-09 | 41 | 30 | 2 | 9 | 15 |
| 2026-07-10 | 45 | 35 | 0 | 10 | 14 |
| 2026-07-11 | 30 | 20 | 1 | 9 | 13 |
| 2026-07-12 | 55 | 47 | 0 | 8 | 12 |
| 2026-07-13 | 10 | 5 | 0 | 5 | 11 |
| 2026-07-14 | 47 | 41 | 1 | 5 | 10 |
| 2026-07-15 | 119 | 97 | 7 | 15 | 9 |
| 2026-07-16 | 113 | 90 | 13 | 10 | 8 |
| 2026-07-17 | 184 | 123 | 39 | 22 | 7 |
| 2026-07-18 | 77 | 44 | 23 | 10 | 6 |
| 2026-07-19 | 105 | 52 | 46 | 7 | 5 |
| 2026-07-20 | 59 | 18 | 39 | 2 | 4 |
| **2026-07-24** | **610** | **143** | **463** | **4** | **0** |
| **TOTAL** | **3,925** | **2,674** | **641** | **610** | |

The "still terrible" column is ~0 for everything older than ten days and
collapses onto the last few rows — the clearest possible statement that terrible
entries are transient.

---

## 4. How the two channels differ, and why both results are right

| measurement | window | population | result |
|---|---|---|---|
| snapshot diff (`addrman_fate.py`) | 1.9 h | *all* terrible entries in addrman | 254 evicted : 1 rescued |
| cohort tracking (`poisoned_fate.py`) | 28 d | only entries we *made* terrible | 2,107 evicted : 540 rescued |

Not a contradiction — different questions.

- **Different horizon.** Eviction is fast, rescue is slow. Over 1.9 h almost
  nothing gets rescued; over weeks, a fifth does.
- **Different population, and this is the real point.** A naturally terrible
  address is terrible *because its node stopped announcing* — it is dead, so
  nothing can refresh it. A poisoned address belonged to a **live** peer that was
  being actively announced when we received it; we falsified its age. Its owner
  is still out there, so gossip can and does re-announce it.

> An address terrible because its node is **dead** leaves addrman only by
> eviction. An address terrible because we **falsified its timestamp** is
> rescued by gossip 20% of the time, because its node is alive.

---

## 5. Caveats

- **Final state only.** An address evicted and later re-learned counts as
  "rescued", not "evicted then returned". 2,674 is net.
- **92 hours of rescue time are missing.** The node was dead 07-20 12:00 →
  07-24 08:52, so the mature cohorts lost four days in which gossip could have
  reached them. The 20.3% rescue share is a floor.
- **"Terrible" is the horizon arm only** — `now − nTime > 30 d`.
  `getrawaddrman` does not expose `nAttempts` / `m_last_try` / `m_last_success`,
  so the three failure-based arms of `IsTerrible()` cannot be evaluated. Eviction
  in `addrman.cpp:585` tests the *full* predicate, so it targets a slightly larger
  set than we can see.
- **Insert attribution is same-second.** An `Added` line counts as "entered via
  this poisoned delivery" only within 2 s of the forcing (`AddSingle` runs
  synchronously inside `ProcessAddrs`). A looser window inflated the entered
  cohort by ~40% by absorbing later, unrelated gossip inserts.
