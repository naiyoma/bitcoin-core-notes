#!/usr/bin/env python3
"""
Eviction accounting straight from debug.log (needs -debug=addrman, which both
nodes already run).

Answers, over the WHOLE log window rather than a two-snapshot keyhole:
  * how many addresses were evicted from the `new` table, per day
  * how many were inserted, per day  (in a saturated table these must match)
  * how full the new table was, over time
  * how long an evicted address had been sitting there before it was killed
  * whether eviction pressure tracks the incoming addr-message volume
    (i.e. did the addr-spam surge do the evicting?)

The log lines it keys off, from src/addrman.cpp:

  ClearNew()          "Removed <ip> from new[b][p]"                  <- EVICTION
  AddSingle()         "Added <ip>[ mapped to ASn] to new[b][p]"      <- INSERT
  MakeTried()         "Moved <ip> to tried[b][p]"                    <- PROMOTION
  MakeTried()         "Moved <ip> from tried[b][p] to new[b][p] ..." <- DEMOTION
  Add()               "Added N addresses (of M) from <src>: T tried, U new"
                                                                     <- OCCUPANCY
  ResolveCollisions() "Collision with <ip> while attempting to move ..."

WHY "Removed" IS EXACTLY THE EVICTION SIGNAL
--------------------------------------------
ClearNew() is reached from only two places:
  1. AddSingle (addrman.cpp:591) -- a newly arrived address hashed to an
     occupied slot AND the incumbent lost the tie-break at line 585:
         infoExisting.IsTerrible() || (infoExisting.nRefCount > 1 && new==0)
     So a "Removed" from this path means the incumbent was terrible (or was a
     multi-bucket entry displaced by a never-seen one).
  2. MakeTried (addrman.cpp:511) -- an entry demoted out of `tried` needs a new
     slot and clears whoever was there.
Promotion to `tried` does NOT log "Removed": MakeTried clears vvNew directly
(addrman.cpp:480-484) without calling ClearNew. So "Removed" never
double-counts a promotion.

Case 1 vs case 2 is separable: case 2 is always immediately followed by
"Moved <ip> from tried[..] to new[b][p] to make space" on the same slot, and
case 1 by "Added <ip> to new[b][p]" on the same slot.

usage: addrman_churn.py <debug.log | debug.log.zst> [--json out.json]
"""
import sys, re, json, subprocess, collections

RE_ADDED_NEW = re.compile(r'^(\S+) \[addrman\] Added (\S+?)(?: mapped to AS\d+)? to new\[(\d+)\]\[(\d+)\]')
RE_REMOVED   = re.compile(r'^(\S+) \[addrman\] Removed (\S+) from new\[(\d+)\]\[(\d+)\]')
RE_TO_TRIED  = re.compile(r'^(\S+) \[addrman\] Moved (\S+?)(?: mapped to AS\d+)? to tried\[(\d+)\]\[(\d+)\]')
RE_DEMOTED   = re.compile(r'^(\S+) \[addrman\] Moved (\S+) from tried\[(\d+)\]\[(\d+)\] to new\[(\d+)\]\[(\d+)\] to make space')
RE_OCCUPANCY = re.compile(r'^(\S+) \[addrman\] Added \d+ addresses \(of \d+\) from \S+: (\d+) tried, (\d+) new')
RE_COLLISION = re.compile(r'^(\S+) \[addrman\] Collision with (\S+) while attempting to move (\S+) to tried table\. Collisions=(\d+)')
# control node tags these "experiment1:", test node "experiment4:" -- same format
RE_EXP4_MSG  = re.compile(r'^(\S+) \[net\] experiment\d+: (gossip addr|getaddr response) from peer=(\d+) size=(\d+)')

NEW_TABLE_CAPACITY = 1024 * 64   # ADDRMAN_NEW_BUCKET_COUNT * ADDRMAN_BUCKET_SIZE


def open_log(path):
    if path.endswith(".zst"):
        p = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE, bufsize=1 << 22)
        return p.stdout, p
    return open(path, "rb"), None


def day(ts):
    return ts[:10]


def main(path, jsonout=None):
    fh, proc = open_log(path)

    daily = collections.defaultdict(lambda: collections.defaultdict(int))
    occupancy = {}                      # day -> (last tried, last new) seen that day
    slot_last_removed = {}              # "b/p" -> (ts, addr) awaiting its successor
    evict_cause = collections.Counter()
    added_at = {}                       # addr -> ts of its most recent insert
    lifetimes = []                      # (evict_ts, addr, seconds_resident)
    evicted_addrs = collections.Counter()
    peer_msgs = collections.Counter()   # (day, peer) -> msgs   [spam attribution]
    n_lines = 0

    for raw in fh:
        n_lines += 1
        line = raw.decode("utf-8", "replace")
        if "[addrman]" not in line and "experiment" not in line:
            continue

        m = RE_REMOVED.match(line)
        if m:
            ts, addr, b, p = m.group(1), m.group(2), m.group(3), m.group(4)
            d = day(ts)
            daily[d]["evicted"] += 1
            evicted_addrs[addr] += 1
            slot_last_removed[f"{b}/{p}"] = (ts, addr)
            if addr in added_at:
                try:
                    from datetime import datetime
                    t0 = datetime.strptime(added_at[addr], "%Y-%m-%dT%H:%M:%SZ")
                    t1 = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                    lifetimes.append((ts, addr, (t1 - t0).total_seconds()))
                except ValueError:
                    pass
            continue

        m = RE_ADDED_NEW.match(line)
        if m:
            ts, addr, b, p = m.group(1), m.group(2), m.group(3), m.group(4)
            d = day(ts)
            daily[d]["inserted"] += 1
            added_at[addr] = ts
            prev = slot_last_removed.pop(f"{b}/{p}", None)
            if prev and prev[1] != addr:
                evict_cause["collision_insert"] += 1
            continue

        m = RE_DEMOTED.match(line)
        if m:
            daily[day(m.group(1))]["demoted_tried_to_new"] += 1
            prev = slot_last_removed.pop(f"{m.group(5)}/{m.group(6)}", None)
            if prev:
                evict_cause["tried_demotion"] += 1
            continue

        m = RE_TO_TRIED.match(line)
        if m:
            daily[day(m.group(1))]["promoted_to_tried"] += 1
            continue

        m = RE_COLLISION.match(line)
        if m:
            daily[day(m.group(1))]["tried_collision"] += 1
            continue

        m = RE_OCCUPANCY.match(line)
        if m:
            ts, tried, new = m.group(1), int(m.group(2)), int(m.group(3))
            occupancy[day(ts)] = (tried, new)
            continue

        m = RE_EXP4_MSG.match(line)
        if m:
            ts, kind, peer, size = m.group(1), m.group(2), m.group(3), int(m.group(4))
            d = day(ts)
            if kind == "gossip addr":
                daily[d]["gossip_msgs"] += 1
                daily[d]["gossip_addrs"] += size
            else:
                daily[d]["getaddr_msgs"] += 1
                daily[d]["getaddr_addrs"] += size
            peer_msgs[(d, peer)] += 1
            continue

    fh.close()
    if proc:
        proc.wait()

    days = sorted(daily)
    P = print
    P(f"parsed {n_lines:,} lines from {path}\n")
    P(f"{'day':<12}{'inserted':>10}{'EVICTED':>10}{'->tried':>9}{'tried->new':>11}"
      f"{'new occ':>10}{'full%':>7}{'gossip addr':>13}{'getaddr addr':>13}")
    for d in days:
        r = daily[d]
        occ = occupancy.get(d)
        occs = f"{occ[1]:,}" if occ else "-"
        fullp = f"{100*occ[1]/NEW_TABLE_CAPACITY:.1f}" if occ else "-"
        P(f"{d:<12}{r['inserted']:>10,}{r['evicted']:>10,}{r['promoted_to_tried']:>9,}"
          f"{r['demoted_tried_to_new']:>11,}{occs:>10}{fullp:>7}"
          f"{r['gossip_addrs']:>13,}{r['getaddr_addrs']:>13,}")

    tot_i = sum(daily[d]["inserted"] for d in days)
    tot_e = sum(daily[d]["evicted"] for d in days)
    P(f"\ntotal inserted {tot_i:,} | total EVICTED {tot_e:,} | "
      f"evict/insert = {tot_e/max(tot_i,1):.3f}")
    P(f"eviction cause (paired by bucket slot): {dict(evict_cause)}")

    if lifetimes:
        secs = sorted(x[2] for x in lifetimes)
        q = lambda f: secs[min(int(f * len(secs)), len(secs) - 1)] / 86400
        P(f"\nresidency before eviction (n={len(secs):,} where the insert is also in "
          f"this log): p10={q(.1):.1f}d p50={q(.5):.1f}d p90={q(.9):.1f}d")
        over30 = sum(1 for s in secs if s > 30 * 86400)
        P(f"  evicted after >30d resident (terrible by horizon unless refreshed): "
          f"{over30:,} ({100*over30/len(secs):.1f}%)")

    rep = evicted_addrs.most_common(10)
    if rep and rep[0][1] > 1:
        P(f"\nmost-repeatedly-evicted addresses: " +
          ", ".join(f"{a}({n})" for a, n in rep[:6]))

    # addr-spam attribution: which peers drove the busiest days
    if peer_msgs:
        by_day = collections.defaultdict(list)
        for (d, peer), n in peer_msgs.items():
            by_day[d].append((n, peer))
        P(f"\n{'day':<12}{'addr msgs':>11}{'peers':>7}   top peers by addr-msg count")
        for d in sorted(by_day):
            lst = sorted(by_day[d], reverse=True)
            tot = sum(n for n, _ in lst)
            top = ", ".join(f"peer{p}:{n:,}" for n, p in lst[:4])
            share = 100 * sum(n for n, _ in lst[:4]) / max(tot, 1)
            P(f"{d:<12}{tot:>11,}{len(lst):>7}   {top}  (top4={share:.0f}%)")

    if jsonout:
        json.dump({"daily": {d: dict(daily[d]) for d in days},
                   "occupancy": occupancy,
                   "evict_cause": dict(evict_cause),
                   "lifetimes_days": sorted(x[2] / 86400 for x in lifetimes),
                   "peer_msgs": {f"{d}|{p}": n for (d, p), n in peer_msgs.items()}},
                  open(jsonout, "w"))
        P(f"\nwrote {jsonout}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    jo = a[a.index("--json") + 1] if "--json" in a else None
    main(a[0], jo)
