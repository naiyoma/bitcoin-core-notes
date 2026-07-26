#!/usr/bin/env python3
"""
Per-day gossip vs getaddr split, cut where Core's own relay gate cuts.

net_processing.cpp ProcessAddrs:

    if (addr.nTime > current_time - 10min && !peer.m_getaddr_sent
            && vAddr.size() <= 10 && addr.IsRoutable()) {
        RelayAddress(pfrom.GetId(), addr, reachable);
    }

`vAddr.size() <= 10` is a per-MESSAGE test, so classifying whole messages by
their logged size is exactly the right instrument:

    size <=  10  -> gossip / relayed self-announcement (Core will propagate it)
    size >=  11  -> getaddr reply (Core will not)

Both node branches log every addr message with its real size, regardless of
which label they applied:
    experiment1|4: gossip addr from peer=N size=M kept real timestamps    (<990)
    experiment1|4: getaddr response from peer=N size=M forced to ...      (>=990)
so the >=990 baked into the node is re-cut here at <=10 without re-reading
anything.

CAVEAT: size<=10 is necessary but not sufficient for the relay gate -- it also
needs !m_getaddr_sent and nTime > now-10min. We only send getaddr to outbound
peers and most gossip arrives inbound, so the leakage is second-order.

usage: addr_channel_daily.py <events.txt | debug.log | debug.log.zst> [--md]
"""
import sys, re, subprocess, collections

RE_MSG = re.compile(
    r'^(\d{4}-\d\d-\d\d)T\S+ \[net\] experiment\d+: '
    r'(?:gossip addr|getaddr response) from peer=(\d+) size=(\d+)')

GOSSIP_MAX = 10          # Core's relay gate
FULL_DUMP  = 990         # the node's own (arbitrary) forcing threshold


def lines(path):
    if path.endswith(".zst"):
        p = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE, bufsize=1 << 22)
        for b in p.stdout:
            yield b.decode("utf-8", "replace")
        p.wait()
    else:
        with open(path, errors="replace") as f:
            yield from f


def main(path, md=False):
    d = collections.defaultdict(lambda: collections.Counter())
    for line in lines(path):
        if "experiment" not in line:
            continue
        m = RE_MSG.match(line)
        if not m:
            continue
        day, size = m.group(1), int(m.group(3))
        r = d[day]
        if size <= GOSSIP_MAX:
            r["g_msgs"] += 1
            r["g_addrs"] += size
            if size == 1:
                r["g_size1"] += 1
        else:
            r["ga_msgs"] += 1
            r["ga_addrs"] += size
            if size >= FULL_DUMP:
                r["ga_full_addrs"] += size

    days = sorted(d)
    if not days:
        sys.exit("no 'experimentN: ... from peer=... size=...' lines found in " + path)

    sep, bar = ("|", "|") if md else (" ", "")
    hdr = ["day", "gossip msgs", "gossip addrs", "getaddr msgs", "getaddr addrs",
           "total addrs", "gossip addr %", "avg gossip size"]
    if md:
        print("| " + " | ".join(hdr) + " |")
        print("|" + "|".join(["---"] * len(hdr)) + "|")
    else:
        print(f"{'day':<12}{'gossip msgs':>13}{'gossip addrs':>14}{'getaddr msgs':>14}"
              f"{'getaddr addrs':>15}{'total addrs':>13}{'gossip%':>9}{'avg g size':>12}")

    tot = collections.Counter()
    for day in days:
        r = d[day]
        tot.update(r)
        ta = r["g_addrs"] + r["ga_addrs"]
        gp = 100 * r["g_addrs"] / ta if ta else 0
        av = r["g_addrs"] / r["g_msgs"] if r["g_msgs"] else 0
        if md:
            print(f"| {day} | {r['g_msgs']:,} | {r['g_addrs']:,} | {r['ga_msgs']:,} | "
                  f"{r['ga_addrs']:,} | {ta:,} | {gp:.1f}% | {av:.2f} |")
        else:
            print(f"{day:<12}{r['g_msgs']:>13,}{r['g_addrs']:>14,}{r['ga_msgs']:>14,}"
                  f"{r['ga_addrs']:>15,}{ta:>13,}{gp:>8.1f}%{av:>12.2f}")

    ta = tot["g_addrs"] + tot["ga_addrs"]
    tm = tot["g_msgs"] + tot["ga_msgs"]
    print()
    print(f"TOTAL over {len(days)} days ({days[0]} .. {days[-1]})")
    print(f"  gossip  (<=10)  msgs  : {tot['g_msgs']:>10,}  ({100*tot['g_msgs']/tm:.1f}% of messages)")
    print(f"  gossip  (<=10)  addrs : {tot['g_addrs']:>10,}  ({100*tot['g_addrs']/ta:.1f}% of addresses)")
    print(f"  getaddr (>=11)  msgs  : {tot['ga_msgs']:>10,}  ({100*tot['ga_msgs']/tm:.1f}% of messages)")
    print(f"  getaddr (>=11)  addrs : {tot['ga_addrs']:>10,}  ({100*tot['ga_addrs']/ta:.1f}% of addresses)")
    print(f"  all messages          : {tm:>10,}")
    print(f"  all addresses         : {ta:>10,}")
    print(f"  avg gossip msg size   : {tot['g_addrs']/max(tot['g_msgs'],1):>10.2f} addr")
    print(f"  size==1 share of <=10 : {100*tot['g_size1']/max(tot['g_msgs'],1):>9.1f}%")
    print(f"  (of the getaddr addrs, {tot['ga_full_addrs']:,} came in >=990 dumps "
          f"= {100*tot['ga_full_addrs']/max(tot['ga_addrs'],1):.1f}%)")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--md"]
    if not a:
        sys.exit(__doc__)
    main(a[0], "--md" in sys.argv)
