# Self-announcement / addr-relay / getaddr — what keeps the addrman fresh?

*Analysis date: 2026-07-17. Built from a full single-pass parse of both nodes'
`debug.log` (`parse_addr_logs.py` → `logparse_control.json`, `logparse_test.json`)
plus point-in-time `getrawaddrman` "terrible rate" readings. Figure:
`self_announce_getaddr.png`.*

## The two nodes

| | host / IP | branch | behaviour |
|---|---|---|---|
| **Control** | `normanode` 170.75.165.140 | `test/normal_node` | observation-only logging, **no** timestamp change |
| **Test** | `test` 170.75.164.168 | `experiment-4-getaddr-timestamps` | same logging **plus** getaddr replies forced to 30 days old |

*(Note: the two machines carry the opposite branch names to what the kick-off
message said — the behaviour above is what is actually deployed and is what
matters.)*

### Two thresholds: what the code logs vs. how we should classify

The experiment's log line is baked in at **`size >= 990`**: a `>=990`-address
message is tagged "getaddr response," everything else "gossip." That same `>=990`
test also triggers the timestamp forcing on the test node — every address in a
`>=990` message has its `nTime` overwritten to `now − 30 days` before it enters the
addrman, so those arrive already "terrible."

But `>=990` is **not** where Bitcoin Core itself draws the gossip line. Core relays
an address onward only when:

```cpp
if (addr.nTime > current_time - 10min && !peer.m_getaddr_sent
        && vAddr.size() <= 10 && addr.IsRoutable()) {
    RelayAddress(pfrom.GetId(), addr, reachable);   // net_processing.cpp:5688
}
```

So the network's own operational definition of "this is gossip / a relayed
self-announcement" is **`vAddr.size() <= 10`** (fresh, not in a getaddr context,
routable). That gives a cleaner three-way split of received messages:

- **`size <= 10`** → **gossip / relayed self-announcement** — the only messages Core
  will propagate. Direct (a peer announcing its own address, `addr == pfrom.addr`)
  and indirect (a peer relaying other nodes' fresh self-announcements) both live
  here and are **not** separated in this data.
- **`size 11–989`** → **small / partial getaddr reply** — a peer with a modest
  addrman, or the tail chunk of a multi-message reply. Core does **not** relay
  these (size > 10), and on the test node they are **not** forced (forcing is
  `>=990`), so they leak into the addrman with real timestamps.
- **`size >= 990`** → **full getaddr dump** — forced to 30 days on the test node.

The original `<990`-vs-`>=990` split lumped the 11–989 band in with gossip; the
corrected numbers below move it to the getaddr side, where Core's relay gate puts
it. (`size <= 10` is necessary, not perfectly sufficient: the gate also needs
`!m_getaddr_sent`, but we only ever send getaddr to outbound peers, and the bulk of
gossip arrives from inbound peers, so this is second-order.)

## The mechanism that makes this measurable

Bitcoin Core only **relays** an address that is younger than ~10 minutes
(`ProcessAddrs`: relay requires `addr.nTime > now − 10min` and that we did **not**
just send getaddr). Therefore:

- **gossip / self-announcement → always arrives FRESH** (age ≈ 0). This is the only
  channel that can *lower* an address's age and pull it out of "terrible."
- **getaddr reply → carries the peer's stored timestamps** (age 0…30 days, mostly
  old). On the test node these are additionally pinned to exactly 30 days.

So the addrman's freshness can only be *maintained* by the fresh channel. getaddr
is a **discovery / bulk-seeding** channel, not a freshness channel.

## What the logs show

### Channel volumes (whole current log)

Classified by the relay-accurate cut (`<=10` = gossip, `11–989` = partial getaddr,
`>=990` = full getaddr dump):

| | Control · 45 days | Test · 22 days |
|---|---|---|
| **gossip / relay** (`<=10`) — msgs | 704,413 (98.6%) | 690,769 (97.1%) |
| **gossip / relay** (`<=10`) — addrs | 1,805,135 (**73.2%**) | 1,922,945 (**77.6%**) |
| partial getaddr (`11–989`) — addrs | 137,705 (5.6%) | 280,857 (11.3%, real ts, **not** forced) |
| full getaddr dump (`>=990`) — addrs | 522,989 (21.2%) | 273,988 (11.1%, **forced terrible**) |
| **all getaddr** (`>=11`) — addr share | **26.8%** | **22.4%** |
| avg gossip (`<=10`) msg size | 2.56 addr | 2.78 addr |
| `size==1` share of `<=10` msgs | 39.8% | 37.0% |

- By **messages**, gossip/relay is ~97–99% of all addr-bearing messages — a
  continuous firehose of tiny (≤10) messages; getaddr of any size is ~1–3%.
- By **addresses**, gossip/relay still delivers ~3× more than getaddr (73–78% vs
  22–27%), and delivers it **fresh**, whereas every getaddr address carries an
  old (control) or forced-30-day (test) timestamp.
  
- **Partial-getaddr leak on the test node:** 280,857 addresses (the 11–989 band)
  entered its addrman with *real* timestamps, because forcing only fires at `>=990`.
  So "every fresh entry on the test node must be gossip" holds cleanly only for the
  forced `>=990` share — this unforced band is a small getaddr channel that can
  contribute some non-gossip fresh entries. It does not change the direction of the
  result (gossip is still ~3–4× the volume and the only *guaranteed*-fresh source),
  but it is why the claim should be stated as "predominantly gossip," not "purely."
- The gossip size histogram (Panel D) is the self-announcement signature: `size=1`
  is the single largest bucket and counts fall off geometrically — each peer
  periodically announces its own address and we relay fresh singletons onward.

> **Figure note:** Panels B–D in `self_announce_getaddr.png` still use the original
> `>=990` cut (getaddr = `>=990`, gossip = `<990`), so their "gossip" series
> includes the 11–989 partial-getaddr band. The corrected `<=10` split above only
> shifts ~5–11% of *addresses* between buckets; the figure's shape and conclusion
> are unchanged. Regenerate with the `<=10` cut if you want them to match exactly.

### The outcome (Panel A) — the decisive result

Current `getrawaddrman` terrible rate:

| | Jun 8 | Jun 9 | Jun 11 | Jun 26 | Jul 2 | **Jul 17** |
|---|---|---|---|---|---|---|
| Control | 0.12% | 0.15% | 0.13% | 0.51% | 1.01% | **1.72%** |
| Test | 5.34% | 4.41% | 4.06% | 3.12% | 2.23% | **0.92%** |

The test node force-fed itself **273,988 thirty-day-old addresses** over 22 days,
and *still* its addrman is **99.08% fresh — fresher than the untouched control**.
The forced getaddr poisoning produced a transient spike right after the code
deployed, and gossip then dragged the terrible rate monotonically down and past
the control line. Poisoning the entire getaddr channel did **not** degrade
addrman freshness.

*(Why the test node even ends up slightly fresher than control: on the control
node, getaddr replies carry **real** timestamps spread across 0–30 days — a
steady trickle of genuinely-aging 20–29-day addresses that later cross into
"terrible" and sit there. On the test node those same addresses are pinned to
exactly 30 days, so they are terrible on arrival and get evicted from the `new`
table quickly instead of lingering. Either way the *fresh* population is set by
gossip, and gossip is slightly heavier on the test node because it has more
inbound peers — 55 vs 37 — hence more relayed traffic.)*

## Answering the question directly

**"If I have old addresses, will self-announcements be enough to trigger an
update, or is it getaddr that triggers the self-announcements?"**

1. **Self-announcements / gossip are sufficient on their own.** They are the only
   channel that delivers fresh (age < 10 min) addresses, so they are the only
   channel that can lift an address out of "terrible." The test node proves
   sufficiency by contradiction: with the getaddr channel deliberately reduced to
   pure poison, gossip alone still held the addrman at >99% fresh. You do **not**
   need getaddr to keep addresses fresh.

2. **getaddr does NOT trigger self-announcements.** Self-announcements run on their
   own schedule — a peer advertises its own address on connection setup and then
   roughly every 24 h, independent of whether anyone sent it a getaddr. What *is*
   true is that both a self-announcement and a getaddr go out at the **same moment**
   on a new outbound connection, so they are *correlated in time but causally
   independent*: connection establishment triggers both; getaddr does not cause
   the announcement. In the logs, gossip flows steadily the entire life of a
   connection (Panel C is roughly flat), whereas getaddr replies are one-shot
   per-connection events (only 274–523 of them total).

3. **What getaddr is actually for:** bulk **discovery** of addresses you have never
   seen — seeding the `new` table with breadth. It is a snapshot of a peer's whole
   addrman (mostly older entries), not a freshness pump. Freshness is a gossip
   property.

4. **The one thing neither channel can do:** refresh a *specific* dead peer's
   address. An address only goes fresh again when **that** node re-announces itself
   (or someone relays it fresh). If the node is offline, no getaddr and no gossip
   will un-terrible its entry — it just ages out and is evicted. "Self-announcement
   refreshes X" specifically means *X's own node is still alive and announcing*.

## Caveats / limits of this analysis

- The `>=990` split is a heuristic (see box above); address-level shares are
  gossip-dominated but not gossip-pure. Message-level and the forcing outcome do
  not depend on the heuristic being perfect.
- The terrible-rate series mixes hand-collected snapshots (Jun 8 – Jul 2) with the
  Jul 17 reading; it is not a continuous series. The **log-derived** channel series
  (Panels B–D) *is* continuous and complete for the current log window
  (control from Jun 3, test from Jun 26; both to Jul 17).
- Nodes were stopped/restarted (control 4×, test 2× in the current logs). Restarts
  cause a burst of fresh outbound connections → a cluster of getaddr replies, which
  is the source of the spikier getaddr days in Panel C. This does not affect the
  totals or the conclusion.
- To attribute *individual* refreshes to gossip vs getaddr without relying on the
  size heuristic, use `attribute_terrible_updates.py` on two close `getrawaddrman`
  snapshots — it dates each update and assigns a channel from the age.

---

# Part 2 — Eviction vs. refresh: what actually drains the terrible pool
*Added 2026-07-24, after recovering both nodes from a full-disk outage. Built
from the complete `debug.log` of both nodes (control 2026-06-03 → 07-24, test
2026-06-26 → 07-20; both archived and sha256-verified) plus `getrawaddrman`
snapshot diffs. Tools: `addrman_churn.py` (log side), `addrman_fate.py`
(snapshot side, supersedes `attribute_terrible_updates.py`).*

## The answer: eviction, essentially 100%

Direct measurement — every address that was terrible in snapshot 1, followed
into snapshot 2:

| | test node | control node |
|---|---|---|
| left the terrible pool by **EVICTION** | **76 (100%)** | **7 (100%)** |
| left by refresh — direct self-announcement | 0 | 0 |
| left by refresh — relayed gossip | 0 | 0 |
| left by refresh — unforced getaddr | 0 | 0 |
| still sitting there, untouched | 3,460 (97.5%) | 1,812 (99.6%) |

Not one terrible address was rescued by a self-announcement, on either node.
The terrible pool drains **only** by eviction.

### Why refresh can never be the mechanism

This is not a quirk of the sampling window — it is definitional. An address is
terrible because nobody has announced it for 30 days (`AddrInfo::IsTerrible`,
`addrman.cpp:59`). The only channel that can lower an address's age is gossip,
and Core relays an address only if `addr.nTime > now − 10min`
(`net_processing.cpp:5688`). So for a terrible entry to be refreshed, **the node
that owns it must be alive and announcing** — but if it were, the entry would
not have gone terrible in the first place. Terribleness and refreshability are
mutually exclusive states. Part 1's point 4 said this; Part 2 measures it.

## The structural cause: the `new` table is saturated

`new` holds 1024 buckets × 64 = **65,536** slots. Both nodes sit at 99.8–100%:

| | new occupancy | inserted/day | evicted/day | evict/insert |
|---|---|---|---|---|
| control, 2026-06-03 (filling) | 28,562 (43.6%) | 14,331 | 384 | 0.03 |
| control, 2026-06-20 | 63,772 (97.3%) | 345 | 82 | 0.24 |
| control, 2026-07-01 | 65,191 (99.5%) | 277 | 226 | 0.82 |
| control, 2026-07-21 | 65,399 (99.8%) | 703 | 672 | **0.96** |
| test, whole window | ~65,480 (99.9%) | 508 | 488 | **0.96** |

Once full, **every insertion must evict an incumbent**, and `AddSingle` picks
the victim with (`addrman.cpp:585`):

```cpp
if (infoExisting.IsTerrible() || (infoExisting.nRefCount > 1 && pinfo->nRefCount == 0)) {
    fInsert = true;   // overwrite the existing new-table entry
}
```

So the incumbent is overwritten **precisely when it is terrible**. Eviction is
not a side effect — it is a targeted terrible-address collector, and its rate is
set by the arrival rate of never-before-seen addresses. Confirmed in the logs:
of 12,190 test-node evictions, **12,153 (99.7%)** were `AddSingle` collisions
(paired `Removed X from new[b][p]` → `Added Y to new[b][p]` on the same slot);
only 37 were tried-table demotions.

Corollary — the whole `new` table turns over fast. Median residency from
insertion to eviction is **13.1 h (test) / 14.0 h (control)**; on the control
node, whose window is long enough to see it, **53.3%** of evicted entries had
been resident >30 days.

## Correction to Part 1: the forced timestamps were mostly a no-op

Part 1 says the test node "force-fed itself 273,988 thirty-day-old addresses."
That is true on the wire but **not** in the addrman. `AddSingle`'s
already-known branch (`addrman.cpp:545-559`) is reached first:

```cpp
const bool currently_online{NodeClock::now() - addr.nTime < 24h};  // 30d old -> false
const auto update_interval{currently_online ? 1h : 24h};           // -> 24h
if (pinfo->nTime < addr.nTime - update_interval - time_penalty) {  // only if stored is >31d old
    pinfo->nTime = std::max(NodeSeconds{0s}, addr.nTime - time_penalty);
}
if (addr.nTime <= pinfo->nTime) { return false; }                  // otherwise: discard
```

A 30-day-old timestamp can therefore **never** make a known entry staler. It is
discarded unless the stored entry is already older than 31 days, in which case
it is nudged *forward* to exactly 30 d (still terrible). The forcing only bit on
**never-before-seen** addresses — and those are rare:

| | addrs received | entered addrman as new entries | share |
|---|---|---|---|
| test | 2,698,828 | 12,704 | **0.47%** |
| control | 2,730,451 | 68,366 | 2.50% |

Even attributing *every* test-node insertion to the getaddr channel, **at most
4.09%** of its 310,979 forced addresses could have landed. ≥95.9% were no-ops.
The experiment's conclusion (gossip keeps the addrman fresh) still holds, but
the mechanism is not "gossip out-ran the poison" — it is "**the poison mostly
never entered**, and what did enter was terrible on arrival and evicted within
hours."

This also explains the crossover where the test node became *fresher* than
control. Test-node getaddr entries arrive already terrible, so they are the
preferred eviction victims and churn straight back out. Control-node getaddr
entries arrive at real ages 0–30 d, enter as non-terrible, then **age into**
terrible in place and sit there until something happens to collide with them.
The control node accumulates; the test node churns.

## A sharper channel discriminator than message size

Part 1 splits channels by message size (`<=10` gossip / `>=990` getaddr). There
is an exact separator that needs no heuristic. `net_processing.cpp:5709` applies
`time_penalty = 2h` to every address from an addr message, and `AddSingle`
(`addrman.cpp:541`) waives it **only** when `addr == source`. Reading the stored
age off `getrawaddrman` therefore gives:

| stored age | channel |
|---|---|
| ≈ 0 | **direct self-announcement** (peer announcing its own address) |
| ≈ 2 h … 2 h 10 m | **relayed gossip** (third party's fresh address, +2 h) |
| ≈ 30 d + 2 h | forced getaddr (test node) |
| anything else < 30 d | unforced getaddr reply, real stored timestamps |

This finally separates *direct* from *relayed* self-announcement, which Part 1
explicitly could not do. Validated on live data: of 78 test-node arrivals in one
interval, 75 landed in the 30 d + 2 h band and 3 in the 2 h band; all 7 control
arrivals landed in the 2 h band. `addrman_fate.py` implements it.

## The addr surge — real, but broad-based, and it did NOT drive eviction

Both nodes saw a network-wide addr-relay surge, same timing, peaking 2026-07-13
and ending abruptly on 07-15:

| gossip addrs/day | 06-26 | 07-05 | 07-10 | **07-13** | 07-15 | 07-20 |
|---|---|---|---|---|---|---|
| test | 33,930 | 94,657 | 143,852 | **252,038** | 81,435 | 29,715 |
| control | 46,293 | 53,342 | 51,931 | **79,931** | 28,057 | 34,435 |

It was **not** a concentrated spammer. As volume rose 7.4× on the test node,
sender concentration *fell* — top-1 peer share 11.7% → 3.4%, top-5 share 52.5% →
16.6%, distinct peers 104 → 350. The load came from more peers each sending
more, not from a few abusers.

**And it produced no extra addrman churn.** Test-node evictions over the same
period went 1,165/day (06-26) → 409/day (07-13) — *down* while volume went up
7.4×. The reason is the same `AddSingle` branch: a re-announcement of an
already-known address updates `nTime` in place and inserts nothing. Only novel
addresses insert, and only insertions evict. **Address volume is not addrman
pressure; address novelty is.** This is worth keeping in mind for the
fingerprinting work — an addr flood is close to free for a saturated addrman.

## Data caveats

- **Both nodes filled their disks** (67 GB) with `debug.log` and stopped.
  Test: last entry 2026-07-20 ~11:55, then dead — its restart failure
  (`settings.json ... does not contain valid JSON`) was a *symptom*; the file was
  0 bytes because the disk was full. Control: gap 2026-07-22 19:xx → 07-24 07:xx.
  Neither gap is a network effect.
- The test node's 4-day outage is why its terrible rate jumped **0.92% (07-17) →
  5.23% (07-24)**: wall-clock kept advancing while no gossip arrived to refresh
  anything. Control, down ~36 h, went 1.72% → 2.71%. This is itself clean
  evidence that the low rates in Part 1 were *actively maintained* by inbound
  gossip, not a stable property.
- The snapshot gaps behind the Part 2 table are short (0.1 h test, 0.8 h
  control), so the absolute counts are small even though the ratio is 100:0.
  Both nodes now write an hourly `getrawaddrman` snapshot to `~/addrman-snaps/`,
  so re-running `addrman_fate.py` over a multi-day gap will tighten this.
- `getrawaddrman` exposes only `nTime`, not `nAttempts`/`m_last_try`/
  `m_last_success`, so "terrible" here is the horizon arm of `IsTerrible()`
  only — a lower bound, and the same definition used throughout Part 1.
