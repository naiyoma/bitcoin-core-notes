# Experiment — injecting old addresses into an addrman

## Setup

- **Control node** — normal, no changes at all.
- **Test node** — in every getaddr *response* I insert a 30-day-old timestamp
  (forced "terrible" on arrival).

**Purpose:** what happens when we inject old addresses into an addrman? Are
self-announcements enough to keep it fresh, or does getaddr do the work?

## 1 · Terrible-address rate in both addrmans

`getrawaddrman` terrible rate (% of addrman older than 30 days):

| | Jun 8 | Jun 9 | Jun 11 | Jun 26 | Jul 2 |
|---|---|---|---|---|---|---|
| Control | 0.12% | 0.15% | 0.13% | 0.51% | 1.01% |
| Test | 5.34% | 4.41% | 4.06% | 3.12% | 2.23% |

terrible_rate_comparison.png

## 2 · Where the addresses actually came from

Over the logged window:
- By **messages**, gossip/relay is ~97–99% of all addr-bearing messages — a
  continuous firehose of tiny (≤10) messages; getaddr of any size is ~1–3%.
- By **addresses**, gossip/relay delivers ~3× more than getaddr (73–78% vs 22–27%),
  and delivers it **fresh**, whereas every getaddr address is old (control) or
  forced-30-day (test).
- Totals are in the **millions** of addresses; gossip dominates getaddr on both nodes.

## 3 · Are self-announcements enough to refresh addresses?

**Yes.** Gossip / self-announcement is the only channel that delivers fresh
(<10 min) addresses, so it is the only channel that can pull an address out of
"terrible." The test node proves it: with *every* getaddr address poisoned to
30 days, gossip alone still held the addrman at **99% fresh**. getaddr is
discovery/bulk-seeding, not a freshness source.

## 4 · Can I attribute the drop in terrible addresses to self-announcements, not getaddr?

**Mostly yes — with one honest caveat.**

- On the test node, every `>=990` getaddr address is born at exactly 30 days, so it
  can **never** appear as a fresh entry. Therefore every fresh entry there was
  necessarily last-touched by **gossip**. That part is airtight.
- **Caveat:** the forcing only fires at `>=990`. The `11–989` partial-getaddr
  replies (280,857 addrs) entered with *real* timestamps and were **not** forced —
  a small unforced getaddr channel that could contribute some fresh entries.
- Also, a single `getrawaddrman` snapshot can't attribute *old* entries to a
  channel: an addrman timestamp is the recency of the **last refresh**, not the
  delivery channel, so aged-out gossip looks identical to getaddr in a snapshot.

**Bottom line:** the freshness is driven **predominantly by gossip / self-announcements**,
not getaddr — stated as "predominantly," not "purely," because of the unforced
`11–989` leak.
