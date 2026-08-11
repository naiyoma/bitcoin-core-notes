# A network-wide drop in addr-relay volume on 2026-07-15

On 2026-07-15 the rate at which the Bitcoin network relayed addresses fell by
roughly half, within a single day, and did not recover. Both experiment nodes saw
it independently. It is measurable on individual TCP connections that were open
before and after the change, which rules out client upgrades, peer churn, and
anything local to these nodes.

This is a finding about the **network**, not about the getaddr/self-announcement
experiment ([[self_announcement_getaddr_findings.md]]). It surfaced while trying
to identify who originated the Jul 5–14 addr surge, and it is the more solid
result of the two.

---

## 1. The controlled measurement

Three peers held single, unbroken connections across the boundary. Same sockets,
same peer ids, no reconnect:

| peer | address | connection span | addresses sent |
|---|---|---|---:|
| 304 | 87.116.132.35 | Jul 2 12:11 → Jul 19 04:08 | 125,671 |
| 5338 | 24.118.234.146 | Jul 3 13:08 → Jul 20 11:54 | 106,442 |
| 6231 | 190.45.87.235 | Jul 3 17:25 → Jul 20 11:55 | 111,008 |

Addresses per addr message, per day:

| day | peer 304 | peer 5338 | peer 6231 |
|---|---:|---:|---:|
| Jul 12 | 4.32 | 4.02 | 4.17 |
| Jul 13 | 4.19 | 3.87 | 4.17 |
| Jul 14 | 3.61 | 3.52 | 3.57 |
| **Jul 15** | **2.25** | **2.12** | **2.23** |
| Jul 16 | 2.17 | 1.89 | 2.19 |
| Jul 17 | 2.15 | 1.83 | 2.25 |

Message counts fell too, ~2,000/day → ~1,300/day per peer, consistent with more
flush intervals expiring empty.

**What this rules out.** A client upgrade requires a restart, which drops the
connection — these connections persisted, so those peers did not upgrade. Our own
nodes did not restart either: peer ids climb monotonically through the boundary.
And it is not composition change, because it is the same three sockets throughout.

---

## 2. The same break, seen three other ways

**Gossip packing, both nodes, permanent:**

| | Jul 13 | Jul 14 | **Jul 15** | Jul 20 |
|---|---:|---:|---:|---:|
| test | 3.51 | 3.02 | **2.12** | 1.90 |
| control | 3.11 | 2.73 | **1.97** | 1.91 |

**Rate-limiting concentration collapses.** Share of a day's rate-limited addresses
attributable to the single worst peer:

| | before Jul 15 | after Jul 15 |
|---|---|---|
| test | 24–85% (typ. 60%) | 1.6–5.2% |
| control | spikes to 48–75% | 1.8–4.2% |

The number of peers rate-limited barely moves (99 → 82 on test). It is not that
fewer peers are affected — no single peer ever exceeds the token bucket again.

**Rate-limiting intensity** on test falls from 100–350 per 10k addresses received
to 18–28.

---

## 3. Why rate-limiting is the sharpest instrument

`MAX_ADDR_RATE_PER_SECOND = 0.1` gives each peer a budget of **8,640
addresses/day**. Peer 304 tracks the threshold exactly:

| day | addresses | rate-limited |
|---|---:|---:|
| Jul 10 | 9,040 | 436 |
| Jul 11 | 8,731 | 96 |
| Jul 12 | 8,614 | 40 |
| Jul 13 | 8,366 | **0** |

Crossing back under the budget zeroes it. So the "concentration collapse" is not
about which peers were involved — it is simply that after Jul 15 no peer sent
enough to exceed the bucket. Rate-limiting is a **node-side** measurement: it
records what our node decided to drop, so unlike anything derived from address
timestamps it cannot be shaped by what peers claim.

---

## 4. The unexplained part

Post-Jul-15 packing settles **below the pre-surge baseline**, on both nodes:

| | pre-surge (Jun 26 – Jul 4) | surge peak (Jul 13) | post-Jul-15 |
|---|---:|---:|---:|
| test | ~3.08 | 3.51 | ~1.99 (−35%) |
| control | ~2.70 | 3.11 | ~1.89 (−30%) |

If the Jul 5–14 surge had merely ended, volume should have returned to ~3.08 and
~2.70. It did not. Whatever happened on Jul 15 left the network relaying
substantially fewer addresses than before the surge began — so "the surge stopped"
is not a sufficient explanation.

---

## 5. What this is not

Two candidate explanations were tested and rejected. Both are recorded because
each cost real effort and each has a reusable methodological lesson.

**Not a crawler.** `/BTC-Nodes:2026-07-14/Sonar/` from `185.156.37.28` looked
promising — its user agent carries a Jul 14 build date, and the top rate-limited
peer ids after the break were all Sonar connections first seen on Jul 15. It is a
constant: 48 connections/day to both nodes, unbroken from Jun 23/26 through Jul 22,
identical either side of the boundary.

> **Lesson: peer ids are per-connection.** "First seen" for a peer id is the time
> that *connection* opened, not when the entity appeared. Selecting peer ids from
> a post-Jul-15 window guarantees post-Jul-15 first-seen times. Always resolve to
> address before reasoning about when something started.

**Not port-39388 address spam.** A distinctive population — 2.3–2.5% of both
addrmans, 818–885 distinct /16 groups, essentially unconnectable (3 tried entries
on test, 1 on control, unchanged across two weeks), constantly re-announced. Its
share of *newly timestamped* entries appeared to jump from ~1% to ~4.5% at Jul 15.
It did not. Normalised against entries refreshed in the last 5 days, it is
**4.7% on 2026-07-24 and 4.7% on 2026-08-06** — flat. And during the surge itself
its share ran 0.6–1.1%, *below* its own baseline: it was diluted by the surge, not
driving it.

> **Lesson: an addrman entry's timestamp is its last refresh, not its arrival.**
> A population that re-announces more often piles up in recent date buckets and
> thins out of old ones, manufacturing a step change out of nothing. Median age
> for `:39388` is 1.5 d against `:8333`'s 23.5 d — that gap alone produced the
> artifact. Any analysis that buckets addrman entries by timestamp must normalise
> for refresh rate.

**Also not a concentrated sender.** The surge is diffuse and becomes more so as it
grows: top-1 sender share falls 20.0% → 5.5% while distinct senders rise 367 → 501,
and the addresses span 5,227 distinct /16 groups out of 8,209. Only 0.1% of addrman
entries are direct self-announcements (`address == source`), so for 99.9% of them
`source` records one relay hop and carries no provenance. **Origin is not
recoverable from a single node's vantage point** — not a limitation of this data,
but of the protocol.

---

## 6. Reproducing

Run-1 logs are archived at `~/node-log-archive/{test,control}-node_debug.log.zst`
(see [[node-log-archive-and-rotation]]). Both extractions are one streaming pass
each, no node access:

```bash
zstd -dc ~/node-log-archive/test-node_debug.log.zst \
  | grep -F 'Received addr:' > run1_recv_test.txt          # 806,281 lines
zstd -dc ~/node-log-archive/test-node_debug.log.zst \
  | grep -E 'receive version message|New outbound peer connected' > run1_ver_test.txt
```

The `Received addr:` line carries size, processed count, rate-limited count and
peer id; the version line carries user agent, peer id and peeraddr. Joining them
on peer id is what makes the per-connection analysis in §1 possible.

Line counts to check against: recv 806,281 (test) / 804,315 (control); version
119,554 (test) / 217,692 (control).

---

## 7. Open questions

1. **What happened on Jul 15?** Not a rollout (no reconnects), not a crawler, not
   the surge merely ending (volume settled below baseline). A coordinated shutdown
   of an address-injection campaign fits the timing, but nothing here proves it.
2. **Why below baseline?** The ~30–35% shortfall against pre-surge is unaccounted
   for.
3. **Corroboration.** These are two nodes on one VPS provider in one /16. A third
   node elsewhere, or public crawler data, would establish whether Jul 15 was
   genuinely global.
4. **What is `:39388`?** Steady-state, unreachable, heavily re-announced, spanning
   800+ /16 groups. Not implicated in the surge, but unexplained. Note `170.75.x`
   — our own provider's range — is its single largest /16.
5. **Control rate-limiting jumped on Jun 26** from ~10/day across 1–10 peers to
   ~127/day across 43 peers, the same day the test node came online. Probably a
   config change deployed to both; unverified.
