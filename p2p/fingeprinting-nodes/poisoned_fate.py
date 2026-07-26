#!/usr/bin/env python3
"""
Fate of every address whose timestamp the experiment actually tampered with.

Better than a snapshot diff, because the log names the exact addresses that were
poisoned -- so we can follow that specific cohort rather than infer from the
population. Inputs:

  forced files   lines "experiment4: addr=<ip:port> forced_nTime=<unix>"
                 -> the cohort: every address whose nTime we overwrote
  event files    lines "[addrman] Added <a> to new[b][p]" / "Removed <a> from new[b][p]"
                 -> whether the poisoned delivery actually landed in addrman
  snapshot       a getrawaddrman capture ({"t": <unix>, "d": {...}})
                 -> where each one stands now

The four outcomes:

  NEVER ENTERED  forced on the wire, but AddSingle discarded it -- the address was
                 already known and addrman.cpp:545-559 refuses to move a known
                 entry's nTime backwards. The forcing was a no-op.
  EVICTED        entered, and is now gone from addrman entirely.
  STILL TERRIBLE entered, still present, nTime still older than 30 days.
  RESCUED        entered, still present, nTime moved forward past the horizon --
                 something re-announced it fresh. This is the only outcome that
                 requires gossip.

usage: poisoned_fate.py <snapshot.json> --forced f1[,f2] --events e1[,e2]
"""
import sys, re, json, datetime, collections

HORIZON = 30 * 86400
RE_FORCED = re.compile(r'^(\S+) \[net\] experiment\d+: addr=(\S+) forced_nTime=(\d+)')
RE_ADDED = re.compile(r'^(\S+) \[addrman\] Added (\S+?)(?: mapped to AS\d+)? to new\[')
RE_REMOVED = re.compile(r'^(\S+) \[addrman\] Removed (\S+) from new\[')


def norm(a):
    """log writes IPv6 as [x]:port; getrawaddrman gives address+port separately"""
    return a[1:].replace("]:", ":", 1) if a.startswith("[") else a


def main(snap_path, forced_files, event_files):
    # addr -> [every forcing timestamp]. Keeping only the LAST one misses
    # addresses that entered addrman on an EARLIER delivery and were merely
    # re-forced later, which undercounted the entered cohort by ~40%.
    forced = collections.defaultdict(list)
    for path in forced_files:
        for line in open(path, errors="replace"):
            m = RE_FORCED.match(line)
            if m:
                forced[norm(m.group(2))].append(m.group(1))
    print(f"cohort: {len(forced):,} distinct addresses had their nTime forced "
          f"(from {sum(1 for _ in forced_files)} log source(s))")

    added, removed = {}, {}
    for path in event_files:
        for line in open(path, errors="replace"):
            m = RE_ADDED.match(line)
            if m:
                added.setdefault(norm(m.group(2)), []).append(m.group(1)); continue
            m = RE_REMOVED.match(line)
            if m:
                removed.setdefault(norm(m.group(2)), []).append(m.group(1))

    o = json.load(open(snap_path))
    cap = o["t"]
    now = {}
    for table in ("new", "tried"):
        for e in o["d"].get(table, {}).values():
            k = f"{e['address']}:{e['port']}"
            if k not in now or e["time"] > now[k][0]:
                now[k] = (e["time"], table)
    print(f"snapshot: {datetime.datetime.fromtimestamp(cap, datetime.timezone.utc):%Y-%m-%d %H:%M:%SZ}"
          f"  {len(now):,} addresses in addrman\n")

    # An address may be forced, dropped, and then legitimately added weeks later
    # by gossip. Only count it as "entered via the poisoned delivery" if the
    # Added line lands within WINDOW seconds of the forcing -- AddSingle runs
    # synchronously inside ProcessAddrs, so a real one is same-second.
    WINDOW = 2
    def near(fts, tss):
        f = datetime.datetime.strptime(fts, "%Y-%m-%dT%H:%M:%SZ")
        for t in tss:
            try:
                d = (datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") - f).total_seconds()
            except ValueError:
                continue
            if 0 <= d <= WINDOW:
                return True
        return False

    fate = collections.Counter()
    ages = []
    by_day = collections.defaultdict(collections.Counter)
    for addr, fts_list in forced.items():
        hit = next((f for f in fts_list if near(f, added.get(addr, []))), None)
        entered = hit is not None
        cur = now.get(addr)
        if cur is None:
            fate["evicted" if entered else "never_entered_gone"] += 1
        elif not entered:
            # present but the poisoned delivery never inserted it -- it is in
            # addrman via some other path, so the forcing did nothing to it
            fate["never_entered_present"] += 1
        elif cap - cur[0] > HORIZON:
            fate["still_terrible"] += 1
        else:
            fate["rescued"] += 1
            ages.append((cap - cur[0]) / 3600)
        if entered:
            k = "evicted" if cur is None else ("still_terrible" if cap - cur[0] > HORIZON else "rescued")
            by_day[hit[:10]][k] += 1

    tot = sum(fate.values())
    ent = fate["evicted"] + fate["still_terrible"] + fate["rescued"]
    P = print
    P("=== did the poisoned delivery actually land in addrman? ===")
    P(f"  ENTERED addrman            : {ent:>8,}  ({100*ent/tot:5.2f}%)")
    P(f"  never entered (no-op)      : {tot-ent:>8,}  ({100*(tot-ent)/tot:5.2f}%)")
    P(f"     ...of which not in addrman at all : {fate['never_entered_gone']:,}")
    P(f"     ...of which present via another path: {fate['never_entered_present']:,}")
    P("")
    P(f"=== fate of the {ent:,} that DID enter ===")
    for k, lab in (("evicted",        "EVICTED (gone from addrman)      "),
                   ("still_terrible", "still present, still terrible    "),
                   ("rescued",        "RESCUED (nTime refreshed, <30 d) ")):
        P(f"  {lab}: {fate[k]:>8,}  ({100*fate[k]/max(ent,1):5.2f}%)")
    P("")
    P("=== the same, split by the day the address was poisoned ===")
    P(f"  {'poisoned':<12}{'entered':>9}{'evicted':>9}{'terrible':>10}{'rescued':>9}{'days':>7}")
    snap = datetime.datetime.fromtimestamp(cap, datetime.timezone.utc)
    mature = collections.Counter()
    for d in sorted(by_day):
        r = by_day[d]; n = sum(r.values())
        exp = (snap - datetime.datetime.strptime(d + "T12:00:00Z", "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=datetime.timezone.utc)).days
        P(f"  {d:<12}{n:>9,}{r['evicted']:>9,}{r['still_terrible']:>10,}{r['rescued']:>9,}{exp:>7}")
        if exp >= 10:
            mature.update(r)
    mn = sum(mature.values())
    if mn:
        P(f"\n  cohorts with >=10 days of exposure ({mn:,} addresses):")
        P(f"    evicted {mature['evicted']:,} ({100*mature['evicted']/mn:.1f}%)  "
          f"still terrible {mature['still_terrible']:,} ({100*mature['still_terrible']/mn:.1f}%)  "
          f"rescued {mature['rescued']:,} ({100*mature['rescued']/mn:.1f}%)")
    if ages:
        ages.sort()
        q = lambda f: ages[min(int(f * len(ages)), len(ages) - 1)]
        P(f"\n  rescued entries' current age: p10={q(.1):.1f} h  p50={q(.5):.1f} h  p90={q(.9):.1f} h")
    P(f"\n  of everything we poisoned, {100*fate['rescued']/tot:.2f}% is alive and fresh today,")
    P(f"  {100*fate['still_terrible']/tot:.2f}% is alive and still terrible, "
      f"{100*fate['evicted']/tot:.2f}% was evicted.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or "--forced" not in a or "--events" not in a:
        sys.exit(__doc__)
    main(a[0], a[a.index("--forced") + 1].split(","), a[a.index("--events") + 1].split(","))
