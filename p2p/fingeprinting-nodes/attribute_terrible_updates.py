#!/usr/bin/env python3
"""
Attribute updates of terrible addresses to gossip vs getaddr, by diffing two
getrawaddrman snapshots — no node code change required.

Capture snapshots with the timestamp baked in, e.g.:
  echo "{\"t\":$(date +%s),\"d\":$(./build/bin/bitcoin-cli getrawaddrman)}" > snap1.json
  # ... wait a while (keep the gap small: a few hours) ...
  echo "{\"t\":$(date +%s),\"d\":$(./build/bin/bitcoin-cli getrawaddrman)}" > snap2.json
  python3 attribute_terrible_updates.py snap1.json snap2.json

WHY THE AGE OF AN UPDATE REVEALS ITS CHANNEL
--------------------------------------------
Bitcoin Core only RELAYS an address that is younger than 10 min
(ProcessAddrs: `addr.nTime > now-10min && !m_getaddr_sent`). So:

  * gossip / relayed addr  -> always arrives FRESH (age ~= 0)
  * unforced getaddr reply -> keeps REAL timestamps: any age 0..~30 days
                              (this is the `size < 990` leak: those replies are
                               NOT forced, so they carry real mid-age times)
  * forced getaddr reply   -> you overwrite it to exactly `now - 30 days`

Therefore, for an address that was TERRIBLE in snap1, its age in snap2 tells you
who touched it (gap = seconds between the two snapshots):

  age2 <= gap + SLACK          -> GOSSIP        (refreshed to ~now; now fresh)
  gap+SLACK < age2 < 30d-SLACK -> GETADDR leak  (real mid-age time; the 25-day case)
  ~30d (30d..30d+gap)          -> GETADDR forced (re-pinned at the boundary; still terrible)
  timestamp unchanged          -> untouched

CAVEAT: age ~= 0 is *mostly* gossip, but an unforced getaddr could occasionally
carry a genuinely <10-min-old address too. The snapshot method can't split those
apart — only per-message logging in the node can. Everything mid-age (hours..30d)
is unambiguously getaddr, since gossip never delivers non-fresh addresses.
"""
import sys, json

HORIZON = 30 * 86400   # ADDRMAN_HORIZON_DAYS -> "terrible" threshold
SLACK   = 3600         # 1h tolerance for snapshot/timing jitter


def load(path):
    o = json.load(open(path))
    cap = o["t"]
    by_addr = {}
    for table in ("new", "tried"):
        for e in o["d"][table].values():
            k = e["address"]
            if k not in by_addr or e["time"] > by_addr[k]:
                by_addr[k] = e["time"]
    return cap, by_addr


def channel(age2, gap):
    """Which channel produced an address sitting at age2 (seconds) in snap2."""
    if age2 <= gap + SLACK:
        return "gossip"                      # arrived fresh -> only gossip relays fresh
    if HORIZON - SLACK <= age2 <= HORIZON + gap + SLACK:
        return "getaddr_forced"              # pinned at ~30 days -> your forcing
    if age2 < HORIZON:
        return "getaddr_leak"                # mid-age real timestamp -> unforced getaddr
    return "other"                           # older than 30d+gap, not at the forced line


def main(p1, p2):
    cap1, a1 = load(p1)
    cap2, a2 = load(p2)
    gap = max(0, cap2 - cap1)

    fate = {"gossip": 0, "getaddr_leak": 0, "getaddr_forced": 0, "other": 0, "untouched": 0}
    new = {"gossip": 0, "getaddr_leak": 0, "getaddr_forced": 0, "other": 0}

    for addr, t2 in a2.items():
        age2 = cap2 - t2
        if addr not in a1:                       # brand-new entry this interval
            new[channel(age2, gap)] += 1
            continue
        t1 = a1[addr]
        if (cap1 - t1) <= HORIZON:               # only care about ones terrible in snap1
            continue
        if t2 <= t1:                             # timestamp never moved
            fate["untouched"] += 1
        else:
            fate[channel(age2, gap)] += 1

    n_terrible1 = sum(1 for a, t in a1.items() if (cap1 - t) > HORIZON)
    print(f"snapshot gap: {gap/3600:.1f} h   terrible in snap1: {n_terrible1}\n")
    print("--- fate of addresses that were TERRIBLE in snap1 ---")
    print(f"  refreshed by GOSSIP (now fresh)            : {fate['gossip']}")
    print(f"  refreshed by GETADDR leak <990 (now fresh) : {fate['getaddr_leak']}")
    print(f"  re-pinned by GETADDR forced (still ~30d)   : {fate['getaddr_forced']}")
    print(f"  advanced but older than 30d+gap (ambiguous): {fate['other']}")
    print(f"  untouched (no update)                      : {fate['untouched']}")
    print("\n--- brand-new entries this interval, by channel ---")
    print(f"  gossip (fresh)           : {new['gossip']}")
    print(f"  getaddr leak <990 (mid)  : {new['getaddr_leak']}")
    print(f"  getaddr forced (~30d)    : {new['getaddr_forced']}")
    print(f"  other                    : {new['other']}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: attribute_terrible_updates.py snap1.json snap2.json")
    main(sys.argv[1], sys.argv[2])
