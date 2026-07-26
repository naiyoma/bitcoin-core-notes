#!/usr/bin/env python3
"""
Decide WHY the terrible rate moves: eviction vs. in-place refresh.

This supersedes attribute_terrible_updates.py, which could only see addresses
that were STILL PRESENT in snap2 -- so it silently dropped the single most
important outcome, an address vanishing from the addrman entirely.

Capture snapshots with the wall-clock baked in:

  echo "{\"t\":$(date +%s),\"d\":$(./build/bin/bitcoin-cli getrawaddrman)}" > snap1.json
  # ... wait 4-12 h ...
  echo "{\"t\":$(date +%s),\"d\":$(./build/bin/bitcoin-cli getrawaddrman)}" > snap2.json
  ./addrman_fate.py snap1.json snap2.json

WHY THIS WORKS
--------------
Two independent facts about addrman let us read the channel off a timestamp:

1. Core only RELAYS an address younger than 10 min (ProcessAddrs:
   `addr.nTime > now-10min && !m_getaddr_sent`). So gossip / self-announcement
   ALWAYS arrives fresh; a getaddr reply carries the peer's stored (old) times.

2. An entry only leaves the `new` table by being overwritten -- AddSingle
   (addrman.cpp:585) evicts the incumbent only when
   `infoExisting.IsTerrible() || (nRefCount > 1 && newcomer nRefCount == 0)`
   -- or by promotion to `tried` (MakeTried). Nothing ages out on a timer.
   With the new table SATURATED (65 536 slots), every insert forces an evict,
   so eviction pressure tracks the arrival rate of never-seen addresses.

So for an address that was terrible in snap1:

  absent from snap2              -> EVICTED       (a colliding insert took its slot)
  now in `tried`, was in `new`   -> PROMOTED      (survived, we connected to it)
  age2 <= gap                    -> REFRESHED by GOSSIP  (only fresh channel)
  gap < age2 < 30d               -> REFRESHED by GETADDR (real mid-age timestamp)
  age2 ~= 30d exactly            -> RE-PINNED by forced getaddr (test node only)
  timestamp unchanged            -> UNTOUCHED     (still sitting there, still terrible)

The rate is a RATIO, so the report also decomposes it into numerator
(terrible count) and denominator (addrman size) so a falling rate caused purely
by the table growing is not mistaken for terrible addresses going away.
"""
import sys, json

HORIZON = 30 * 86400   # ADDRMAN_HORIZON -> the "not seen in recent history" test
PENALTY = 2 * 3600     # net_processing.cpp:5709 Add(..., time_penalty=2h)
RELAY_W = 600          # relay gate: addr.nTime > now-10min
SLACK   = 900          # snapshot jitter / clock skew


def channel_of(age, gap):
    """Which arrival path produced an entry now sitting at `age` seconds old?

    The 2h time_penalty in net_processing.cpp:5709 is applied to EVERY address
    learned from an addr message -- except when addr == source, where AddSingle
    (addrman.cpp:541) zeroes it because a node announcing itself needs no
    penalty. That gives a free, exact separator the size<=10 heuristic cannot
    match:

        age ~= 0        -> DIRECT self-announcement (addr == source, no penalty)
        age ~= 2h       -> RELAYED gossip (someone else's fresh addr, +2h)
        age ~= 30d + 2h -> forced getaddr on the test node (+2h on top)
        anything else   -> unforced getaddr reply carrying real stored times
    """
    if age <= gap + SLACK:
        return "self_announce_direct"
    if PENALTY - SLACK <= age <= PENALTY + RELAY_W + gap + SLACK:
        return "gossip_relayed"
    if HORIZON + PENALTY - SLACK <= age <= HORIZON + PENALTY + RELAY_W + gap + SLACK:
        return "getaddr_forced"
    if age < HORIZON:
        return "getaddr_unforced"
    return "older_than_horizon"


def load(path):
    o = json.load(open(path))
    cap = o["t"]
    ent = {}   # "ip:port" -> {"time": t, "table": "new"|"tried"}
    for table in ("new", "tried"):
        for e in o["d"].get(table, {}).values():
            k = f"{e['address']}:{e['port']}"
            prev = ent.get(k)
            # an address can occupy several new buckets; keep the freshest, and
            # let `tried` win over `new` since promotion is the stronger fact
            if prev is None or e["time"] > prev["time"] or table == "tried":
                ent[k] = {"time": e["time"],
                          "table": "tried" if (table == "tried" or (prev or {}).get("table") == "tried") else "new"}
    return cap, ent


def is_terrible(cap, t):
    """Horizon arm of AddrInfo::IsTerrible. The other three arms depend on
    nAttempts / m_last_try / m_last_success, which getrawaddrman does not
    expose -- so this is a lower bound, and matches how the rate was measured."""
    return (cap - t) > HORIZON


def main(p1, p2):
    cap1, a1 = load(p1)
    cap2, a2 = load(p2)
    gap = max(0, cap2 - cap1)

    terrible1 = {k: v for k, v in a1.items() if is_terrible(cap1, v["time"])}

    CHANNELS = ["self_announce_direct", "gossip_relayed", "getaddr_unforced",
                "getaddr_forced", "older_than_horizon"]
    fate = dict.fromkeys(["evicted", "promoted_to_tried", "untouched"] + CHANNELS, 0)
    evicted_examples = []

    for k, v1 in terrible1.items():
        v2 = a2.get(k)
        if v2 is None:
            fate["evicted"] += 1
            if len(evicted_examples) < 5:
                evicted_examples.append((k, round((cap1 - v1["time"]) / 86400, 1)))
            continue
        if v2["table"] == "tried" and v1["table"] == "new":
            fate["promoted_to_tried"] += 1
            continue
        if v2["time"] <= v1["time"]:
            fate["untouched"] += 1
        else:
            fate[channel_of(cap2 - v2["time"], gap)] += 1

    # brand-new arrivals this interval, by the channel their timestamp implies
    arrivals = dict.fromkeys(CHANNELS, 0)
    for k, v2 in a2.items():
        if k not in a1:
            arrivals[channel_of(cap2 - v2["time"], gap)] += 1

    n1, n2 = len(a1), len(a2)
    t1n, t2n = len(terrible1), sum(1 for v in a2.values() if is_terrible(cap2, v["time"]))
    r1, r2 = 100 * t1n / max(n1, 1), 100 * t2n / max(n2, 1)

    P = print
    P(f"gap between snapshots: {gap/3600:.1f} h\n")
    P("=== the ratio, decomposed ===")
    P(f"  addrman size      : {n1:>7,}  ->  {n2:>7,}   ({n2-n1:+,})")
    P(f"  terrible count    : {t1n:>7,}  ->  {t2n:>7,}   ({t2n-t1n:+,})")
    P(f"  terrible rate     : {r1:>6.2f}%  ->  {r2:>6.2f}%   ({r2-r1:+.2f} pp)")
    if n2 != n1 and t1n:
        # what the rate would have been if only the denominator had moved
        P(f"  rate if terrible count had NOT changed: {100*t1n/max(n2,1):.2f}%"
          f"  <- denominator-only effect")
    P("")

    P(f"=== fate of the {t1n:,} addresses that were TERRIBLE in snap1 ===")
    order = ["evicted", "untouched", "self_announce_direct", "gossip_relayed",
             "getaddr_unforced", "getaddr_forced", "promoted_to_tried",
             "older_than_horizon"]
    label = {
        "evicted":              "EVICTED (gone from addrman)             ",
        "untouched":            "untouched (still terrible, still in)    ",
        "self_announce_direct": "REFRESHED by DIRECT self-announcement   ",
        "gossip_relayed":       "REFRESHED by RELAYED gossip (+2h penalty)",
        "getaddr_unforced":     "refreshed by unforced getaddr (mid-age) ",
        "getaddr_forced":       "re-pinned by forced getaddr (~30d+2h)   ",
        "promoted_to_tried":    "promoted new -> tried                   ",
        "older_than_horizon":   "advanced but still >30d                 ",
    }
    for k in order:
        pct = 100 * fate[k] / max(t1n, 1)
        P(f"  {label[k]}: {fate[k]:>7,}  ({pct:5.1f}%)")

    gone = fate["evicted"]
    fixed = (fate["self_announce_direct"] + fate["gossip_relayed"]
             + fate["getaddr_unforced"])
    P("")
    P("=== the answer ===")
    if gone + fixed == 0:
        P("  no terrible address changed state in this interval -- widen the gap.")
    else:
        P(f"  left the terrible pool by EVICTION : {gone:>7,}  ({100*gone/(gone+fixed):.1f}%)")
        P(f"  left the terrible pool by REFRESH  : {fixed:>7,}  ({100*fixed/(gone+fixed):.1f}%)")
        P(f"    ...direct self-announcement      : {fate['self_announce_direct']:>7,}")
        P(f"    ...relayed gossip                : {fate['gossip_relayed']:>7,}")
        P(f"    ...unforced getaddr              : {fate['getaddr_unforced']:>7,}")
    if evicted_examples:
        P(f"\n  sample evicted (age at snap1): " +
          ", ".join(f"{k} {d}d" for k, d in evicted_examples))

    P(f"\n=== brand-new entries this interval ({sum(arrivals.values()):,}) ===")
    for c in CHANNELS:
        P(f"  {label[c] if c in label else c:<41}: {arrivals[c]:,}")
    P("\n  NOTE: every arrival into a saturated new table forces one eviction,")
    P("  so 'brand-new entries' is also the eviction pressure for this interval.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
