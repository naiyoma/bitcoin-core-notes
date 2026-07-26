#!/usr/bin/env python3
"""
Per-day getaddr vs gossip counts, taken from Bitcoin Core's STOCK log line
rather than any experiment patch:

  Received addr: 1000 addresses (1000 processed, 0 rate-limited) from peer=8

Why this line and not the experiment1/experiment4 lines: it is emitted by
unpatched Core (net_processing.cpp, end of ProcessAddrs), it carries the raw
message size, and it additionally reports how many addresses survived the
rate limiter -- rate-limited addresses are DROPPED before ever reaching
addrman, so `addresses` overstates what the node acted on.

Channel cut is Core's own relay gate (ProcessAddrs):

    vAddr.size() <= 10  -> gossip / relayed self-announcement
    vAddr.size() >= 11  -> getaddr reply

usage: addr_daily_from_recvaddr.py <recvaddr.txt | debug.log | debug.log.zst>
       [--transpose]   days as columns instead of rows
"""
import sys, re, subprocess, collections

RE = re.compile(
    r'^(\d{4}-\d\d-\d\d)T\S+ \[net\] Received addr: (\d+) addresses '
    r'\((\d+) processed, (\d+) rate-limited\) from peer=(\d+)')

GOSSIP_MAX = 10


def lines(path):
    if path.endswith(".zst"):
        p = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE, bufsize=1 << 22)
        for b in p.stdout:
            yield b.decode("utf-8", "replace")
        p.wait()
    else:
        with open(path, errors="replace") as f:
            yield from f


def main(path, transpose=False):
    d = collections.defaultdict(collections.Counter)
    peers = collections.defaultdict(lambda: collections.defaultdict(set))
    for line in lines(path):
        if "Received addr: " not in line:
            continue
        m = RE.match(line)
        if not m:
            continue
        day, n, proc, rl, peer = (m.group(1), int(m.group(2)), int(m.group(3)),
                                  int(m.group(4)), m.group(5))
        r = d[day]
        if n <= GOSSIP_MAX:
            r["g_msgs"] += 1; r["g_addrs"] += n; r["g_proc"] += proc
            peers[day]["g"].add(peer)
        else:
            r["ga_msgs"] += 1; r["ga_addrs"] += n; r["ga_proc"] += proc
            peers[day]["ga"].add(peer)
            if n >= 990:
                r["full_msgs"] += 1; r["full_addrs"] += n
        r["rate_limited"] += rl

    days = sorted(d)
    if not days:
        sys.exit("no 'Received addr:' lines in " + path)

    ROWS = [("Getaddr messages",  "ga_msgs"),
            ("Getaddr addresses", "ga_addrs"),
            ("Gossip messages",   "g_msgs"),
            ("Gossip addresses",  "g_addrs")]

    if transpose:
        w = 12
        print(f"{'':<20}" + "".join(f"{x[5:]:>{w}}" for x in days))
        for label, key in ROWS:
            print(f"{label:<20}" + "".join(f"{d[x][key]:>{w},}" for x in days))
    else:
        print(f"{'day':<12}{'Getaddr msgs':>14}{'Getaddr addrs':>15}"
              f"{'Gossip msgs':>13}{'Gossip addrs':>14}"
              f"{'rate-limited':>14}{'ga peers':>10}{'gossip peers':>14}")
        for x in days:
            r = d[x]
            print(f"{x:<12}{r['ga_msgs']:>14,}{r['ga_addrs']:>15,}"
                  f"{r['g_msgs']:>13,}{r['g_addrs']:>14,}"
                  f"{r['rate_limited']:>14,}{len(peers[x]['ga']):>10,}"
                  f"{len(peers[x]['g']):>14,}")

    t = collections.Counter()
    for x in days:
        t.update(d[x])
    ta = t["g_addrs"] + t["ga_addrs"]
    tm = t["g_msgs"] + t["ga_msgs"]
    print()
    print(f"TOTAL over {len(days)} days ({days[0]} .. {days[-1]})")
    print(f"  Getaddr messages  : {t['ga_msgs']:>10,}  ({100*t['ga_msgs']/tm:.1f}% of messages)")
    print(f"  Getaddr addresses : {t['ga_addrs']:>10,}  ({100*t['ga_addrs']/ta:.1f}% of addresses)")
    print(f"  Gossip messages   : {t['g_msgs']:>10,}  ({100*t['g_msgs']/tm:.1f}% of messages)")
    print(f"  Gossip addresses  : {t['g_addrs']:>10,}  ({100*t['g_addrs']/ta:.1f}% of addresses)")
    print(f"  all messages      : {tm:>10,}")
    print(f"  all addresses     : {ta:>10,}")
    print(f"  of the getaddr addrs, {t['full_addrs']:,} arrived in {t['full_msgs']:,} "
          f">=990 dumps ({100*t['full_addrs']/max(t['ga_addrs'],1):.1f}%)")
    print(f"  RATE-LIMITED (dropped before addrman): {t['rate_limited']:,} "
          f"({100*t['rate_limited']/ta:.2f}% of all received)")
    print(f"  actually processed into addrman      : {t['g_proc']+t['ga_proc']:,}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        sys.exit(__doc__)
    main(a[0], "--transpose" in sys.argv)
