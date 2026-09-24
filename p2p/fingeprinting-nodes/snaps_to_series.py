#!/usr/bin/env python3
"""
Build terrible_rate_series.json readings from the hourly getrawaddrman snaps.

Run 1's series was typed by hand from point-in-time captures. Since 2026-07-24
both nodes carry `3 * * * * ~/snap-addrman.sh`, writing
~/addrman-snaps/<ts>.json.zst hourly, so the series can be derived instead.

Terrible rate here = share of entries with now - nTime > 30 days
(ADDRMAN_HORIZON, the first arm of AddrInfo::IsTerrible). getrawaddrman does
not expose nAttempts / m_last_try / m_last_success, so the other three arms
cannot be evaluated and every figure is a LOWER BOUND -- same caveat run 1
carried, kept here so it travels with the data.

"now" is the snapshot's own `t`, not wall-clock at analysis time. A snap read a
week later must still be scored against the moment it was taken.

Counts SLOT OCCUPANCY, not distinct addresses -- an address sitting in several
new buckets is counted once per bucket. That is deliberate: it reproduces run
1's cron readings (control 2026-07-24 read 1,819/67,128, and 67,128 only makes
sense as occupied slots against the 1024x64 new table). addrman_fate.py dedupes
by address:port instead, so its population is smaller; the two are answering
different questions and their totals are not meant to agree.

usage:
  snaps_to_series.py --node test    ~/snaps-test/*.json.zst    [--every 6]
  snaps_to_series.py --node control ~/snaps-control/*.json.zst [--every 6]
      [-o series.json]     merge into this file, creating it if absent
      [--every N]          keep one reading per N hours (hourly is far denser
                           than the figure can show; 6 is a readable default)
      [--from YYYY-MM-DD]  ignore snapshots before this date
      [--outage FROM,TO]   record a dead span, ISO8601 Z, repeatable

Seeding the output file with the previous run's series (cp terrible_rate_series
.json ...) gives one continuous line across both runs, with the downtime between
them drawn as an outage. Starting from an empty file plus --from gives the
recent window on its own. Both are legitimate; the first answers "how has this
node behaved since the experiment began", the second "what is it doing now".

Snapshot format, as written by snap-addrman.sh:
    {"t": <unix>, "d": {"new": [...], "tried": [...]}}
"""
import sys, json, os, glob, datetime, subprocess

HORIZON = 30 * 24 * 3600


def load(path):
    if path.endswith(".zst"):
        raw = subprocess.run(["zstd", "-dc", path], capture_output=True,
                             check=True).stdout
    else:
        raw = open(path, "rb").read()
    return json.loads(raw)


def entries(d):
    """getrawaddrman returns {"new": {...}, "tried": {...}} keyed by
    "bucket/position"; both tables count toward the rate."""
    for table in ("new", "tried"):
        t = d.get(table, {})
        for v in (t.values() if isinstance(t, dict) else t):
            yield v


def filename_time(path):
    """Capture time from the snap-addrman.sh filename (20260724T090727Z.json.zst),
    so --every can stride BEFORE decompressing. Returns None if unparseable, in
    which case the file gets opened and its own "t" is used."""
    stem = os.path.basename(path).split(".")[0]
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.datetime.strptime(stem, fmt)
        except ValueError:
            pass
    if stem.isdigit():
        return datetime.datetime.fromtimestamp(int(stem), datetime.timezone.utc
                                               ).replace(tzinfo=None)
    return None


def capture_time(snap, path):
    """snap-addrman.sh may or may not wrap the RPC output with its own "t".
    If it doesn't, fall back to the unix timestamp in the filename, then to
    the file mtime -- anything but wall-clock-now, which would score an old
    snapshot as if it had just been taken and hide every terrible entry."""
    if isinstance(snap, dict) and "t" in snap:
        return int(snap["t"])
    stem = os.path.basename(path).split(".")[0]
    if stem.isdigit():
        return int(stem)
    return int(os.path.getmtime(path))


def reading(path):
    snap = load(path)
    now = capture_time(snap, path)
    d = snap["d"] if isinstance(snap, dict) and "d" in snap else snap
    total = terrible = 0
    for e in entries(d):
        total += 1
        if now - int(e["time"]) > HORIZON:
            terrible += 1
    if not total:
        return None
    return {"t": datetime.datetime.fromtimestamp(
                now, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rate": round(100 * terrible / total, 2),
            "terrible": terrible, "total": total, "src": "cron"}


def main(node, paths, out, every, outages, since=None):
    series = {"readings": {"control": [], "test": []}, "outages": {}}
    if os.path.exists(out):
        series = json.load(open(out))
    series.setdefault("readings", {}).setdefault(node, [])

    # keyed by timestamp so re-running over an overlapping glob updates in place
    # rather than drawing the same hour twice
    by_t = {r["t"]: r for r in series["readings"][node]}

    # Stride on the filename clock first -- decompressing 300+ 2 MB snapshots
    # only to discard 9 in 10 of them is minutes of work for nothing.
    todo, last, gaps = [], None, []
    for p in sorted(paths):
        ft = filename_time(p)
        if ft is None:                      # unparseable name: parse it and let
            todo.append(p)                  # capture_time sort it out
            continue
        if since and ft < since:
            continue
        if last is not None:
            dt = (ft - last).total_seconds()
            if dt > 2 * 3600 and dt > every * 3600 * 1.5:
                gaps.append((last, ft, dt / 3600))
            if dt < every * 3600:
                continue
        last = ft
        todo.append(p)

    # Always keep the newest snapshot, whatever the stride landed on. It is the
    # value read off the right-hand end of the chart, and letting it depend on
    # which snapshot the stride happened to start from moved it by 0.1 pp.
    newest = max((p for p in paths if filename_time(p)
                  and (not since or filename_time(p) >= since)),
                 key=filename_time, default=None)
    if newest and newest not in todo:
        todo.append(newest)

    kept = None
    for p in todo:
        try:
            r = reading(p)
        except Exception as exc:
            print(f"  skip {os.path.basename(p)}: {exc}", file=sys.stderr)
            continue
        if r is None:
            continue
        by_t[r["t"]] = r
        kept = r

    # A missing hour is either a cron miss or a node that was down. The script
    # cannot tell which, so it reports rather than inventing an outage span --
    # an outage drawn where none happened is as misleading as one omitted.
    if gaps:
        print(f"  gaps in {node} snapshots (>2 h between kept snaps):")
        for a, b, h in gaps:
            print(f"    {a:%Y-%m-%dT%H:%M:%SZ} -> {b:%Y-%m-%dT%H:%M:%SZ}  ({h:.1f} h)")
        print("    check these against the node before deciding they are outages")

    series["readings"][node] = sorted(by_t.values(), key=lambda r: r["t"])
    for span in outages:
        a, b = span.split(",")
        spans = series.setdefault("outages", {}).setdefault(node, [])
        if [a, b] not in spans:
            spans.append([a, b])
        spans.sort()

    with open(out, "w") as f:
        json.dump(series, f, indent=1)
    n = len(series["readings"][node])
    print(f"wrote {out}: {node} now has {n} readings"
          + (f", latest {kept['t']} {kept['rate']}% "
             f"({kept['terrible']:,}/{kept['total']:,})" if kept else ""))


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--node" not in a:
        sys.exit(__doc__)
    node = a[a.index("--node") + 1]
    out = a[a.index("-o") + 1] if "-o" in a else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "terrible_rate_series_run2.json")
    every = float(a[a.index("--every") + 1]) if "--every" in a else 6
    outages = [a[i + 1] for i, v in enumerate(a) if v == "--outage"]
    since = (datetime.datetime.strptime(a[a.index("--from") + 1], "%Y-%m-%d")
             if "--from" in a else None)
    consumed = set()
    for i, v in enumerate(a):
        if v in ("--node", "-o", "--every", "--outage", "--from"):
            consumed |= {i, i + 1}
    paths = [v for i, v in enumerate(a) if i not in consumed and not v.startswith("-")]
    paths = [q for p in paths for q in (glob.glob(os.path.expanduser(p)) or [p])]
    if not paths:
        sys.exit("no snapshots matched")
    main(node, paths, out, every, outages, since)
