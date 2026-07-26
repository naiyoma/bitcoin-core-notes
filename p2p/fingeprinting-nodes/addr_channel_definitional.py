#!/usr/bin/env python3
"""
Per-day gossip vs getaddr — split by SOLICITATION, not by message size.

Two categories, as intended:

  getaddr  a reply to a GETADDR we sent
  gossip   everything else, including BOTH direct self-announcement
           (addr == source) and relayed third-party announcements

Why this beats the size cut. `vAddr.size() <= 10` is a heuristic: it is the
gate Core uses to decide whether to RELAY what it received, not a statement
about where the message came from. It leaves an ambiguous 11-989 band that
could be either a small getaddr reply or a busy peer's relay-queue flush.

The definitional fact is in net_processing.cpp:

    bool send_getaddr{false};
    if (!pfrom.IsInboundConn()) { send_getaddr = SetupAddressRelay(pfrom, peer); }
    if (send_getaddr) {
        MakeAndPushMessage(pfrom, NetMsgType::GETADDR);
        peer.m_getaddr_sent = true;
    }

GETADDR goes out ONCE per connection, only to outbound peers, never to
block-relay-only ones. So a peer we never asked CANNOT be replying -- that
half of the classification is exact, no heuristic involved.

For peers we did ask, solicitation alone is not enough: a peer announces its
own address at connection setup, which is the same moment our GETADDR goes
out, so a small message arriving seconds later is a self-announcement and not
a reply. Size disambiguates that case cleanly, because a reply is
`min(1000, 23% of the peer's addrman)` and any established node saturates at
1000 -- there is nothing in between (measured: zero messages sized 100-499
across 806,281 messages).

So:
    peer never solicited                      -> gossip   (definitional)
    solicited, >= MIN_REPLY, within WINDOW    -> getaddr
    anything else                             -> gossip

usage: addr_channel_definitional.py <recvaddr.txt> <getaddr_sent.txt> [--md]
"""
import sys, re, datetime, collections

RE_SENT = re.compile(r'^(\S+) \[net\] sending getaddr \(0 bytes\) peer=(\d+)')
RE_RECV = re.compile(r'^(\S+) \[net\] Received addr: (\d+) addresses '
                     r'\((\d+) processed, (\d+) rate-limited\) from peer=(\d+)')

WINDOW = 120      # seconds after our GETADDR in which a reply is credible
MIN_REPLY = 100   # a real reply saturates near 1000; nothing legitimate sits
                  # between 100 and 989, so this threshold is not load-bearing


def parse(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def main(recv_path, sent_path, md=False):
    # Peer ids are unique only WITHIN a bitcoind run -- they restart at 0 on
    # every start. So the two streams must be merged chronologically and
    # `sent[peer]` kept as the most recent GETADDR seen so far; building the
    # map up front instead matches a post-restart reply against the previous
    # run's peer of the same id, producing bogus 100+ hour "delays".
    events = []
    for line in open(sent_path, errors="replace"):
        m = RE_SENT.match(line)
        if m:
            events.append((m.group(1), "sent", m.group(2), None))
    for line in open(recv_path, errors="replace"):
        m = RE_RECV.match(line)
        if m:
            events.append((m.group(1), "recv", m.group(5),
                           (int(m.group(2)), int(m.group(3)), int(m.group(4)))))
    events.sort(key=lambda e: e[0])

    sent = {}
    daily = collections.defaultdict(collections.Counter)
    unsolicited_big = 0
    for tsraw, kind, peer, payload in events:
        if kind == "sent":
            sent[peer] = parse(tsraw)
            continue
        n, proc, rl = payload
        ts = parse(tsraw)
        day = tsraw[:10]
        t0 = sent.get(peer)
        is_reply = (t0 is not None and n >= MIN_REPLY
                    and 0 <= (ts - t0).total_seconds() <= WINDOW)
        if not is_reply and n >= MIN_REPLY:
            unsolicited_big += 1
        r = daily[day]
        pre = "ga" if is_reply else "g"
        r[pre + "_msgs"] += 1; r[pre + "_addrs"] += n; r[pre + "_proc"] += proc
        r["rate_limited"] += rl

    days = sorted(daily)
    print(f"GETADDR sent {sum(1 for e in events if e[1] == chr(115)+chr(101)+chr(110)+chr(116)):,} times over the window\n")
    print(f"{'day':<12}{'Getaddr msgs':>14}{'Getaddr addrs':>15}"
          f"{'Gossip msgs':>13}{'Gossip addrs':>14}{'gossip % addrs':>16}")
    tot = collections.Counter()
    for d in days:
        r = daily[d]; tot.update(r)
        ta = r["g_addrs"] + r["ga_addrs"]
        print(f"{d:<12}{r['ga_msgs']:>14,}{r['ga_addrs']:>15,}"
              f"{r['g_msgs']:>13,}{r['g_addrs']:>14,}"
              f"{100*r['g_addrs']/max(ta,1):>15.1f}%")

    ta = tot["g_addrs"] + tot["ga_addrs"]; tm = tot["g_msgs"] + tot["ga_msgs"]
    print(f"\nTOTAL over {len(days)} days ({days[0]} .. {days[-1]})")
    print(f"  getaddr : {tot['ga_msgs']:>9,} msgs  {tot['ga_addrs']:>10,} addrs"
          f"  ({100*tot['ga_addrs']/ta:.1f}% of addresses)")
    print(f"  gossip  : {tot['g_msgs']:>9,} msgs  {tot['g_addrs']:>10,} addrs"
          f"  ({100*tot['g_addrs']/ta:.1f}% of addresses)")
    print(f"  all     : {tm:>9,} msgs  {ta:>10,} addrs")
    print(f"  rate-limited (dropped before addrman): {tot['rate_limited']:,}")
    print(f"\n  large (>={MIN_REPLY}) messages NOT matched to a GETADDR we sent: "
          f"{unsolicited_big:,}")
    print("  (those are unsolicited bulk pushes -- counted as gossip here, but")
    print("   they are the population worth looking at for fingerprinting)")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) < 2:
        sys.exit(__doc__)
    main(a[0], a[1], "--md" in sys.argv)
