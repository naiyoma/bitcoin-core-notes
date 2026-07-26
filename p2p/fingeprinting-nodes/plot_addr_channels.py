#!/usr/bin/env python3
"""
Per-day addr channel plot: messages, addresses, rate-limited — one node.

Three panels stacked on a SHARED date axis rather than three separate figures,
because the point of the data is that the panels disagree: around 2026-07-15 the
getaddr message count collapses ~12x while getaddr *addresses* barely move. That
is only visible when the panels line up vertically.

Messages and addresses deliberately do NOT share a y-axis (no dual-axis) --
they are different measures on different scales, so they get their own panels.
Panel A is log-scaled because gossip and getaddr message counts differ hugely.

The channel split is DEFINITIONAL, not the old size heuristic: a message counts
as getaddr only if we logged "sending getaddr ... peer=N" to that same peer, in
the same bitcoind run, within seconds. Everything else -- including direct and
relayed self-announcement -- is gossip. See addr_channel_definitional.py.

usage: plot_addr_channels.py [test|control] [--dark] [-o out.png]
"""
import sys, json, datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

HERE = "/home/ubuntu/Projects/bitcoin-core-notes/p2p/fingeprinting-nodes"

# Validated categorical slots 1 & 2 (see dataviz references/palette.md).
# node validate_palette.js "#2a78d6,#eb6834" --mode light  -> ALL PASS
# node validate_palette.js "#3987e5,#d95926" --mode dark   -> ALL PASS
THEME = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", ink3="#8a8880",
                  grid="#e4e3df", band="#dedcd5", gossip="#2a78d6", getaddr="#eb6834"),
    "dark":  dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", ink3="#83817a",
                  grid="#2f2f2d", band="#333330", gossip="#3987e5", getaddr="#d95926"),
}

# Coverage handling, driven by the "hours" field in the JSON (distinct hours that
# carry any log line that day) rather than a hardcoded list:
#   < MIN_HOURS  -> dropped entirely; too little of the day to be a daily rate
#                   (control's 2026-07-24 holds 2 h, and plotted it read as a
#                    collapse to zero rather than as a log rotation)
#   6..23 h      -> kept but shaded, so a low point is not misread as a real drop
#   24 h         -> plain
MIN_HOURS = 6

TITLE = {"test": "Test node (getaddr replies forced to 30 days old)",
         "control": "Control node (unmodified timestamps)"}


def thousands(v, _):
    if v >= 1000 and v == int(v):
        return f"{int(v):,}"
    return f"{v:g}" if v < 1000 else f"{v:,.0f}"


def main(node="test", dark=False, out=None):
    c = THEME["dark" if dark else "light"]
    raw = json.load(open(f"{HERE}/addr_daily_{node}.json"))
    allday = sorted(raw)
    days = [d for d in allday if raw[d].get("hours", 24) >= MIN_HOURS]
    dropped = [(d, raw[d].get("hours", 24)) for d in allday if d not in days]
    partial = {d for d in days if raw[d].get("hours", 24) < 24}
    x = [datetime.date.fromisoformat(d) for d in days]
    g = lambda k: [raw[d].get(k, 0) for d in days]
    if dropped:
        print("  dropped (<%dh coverage): %s" % (
            MIN_HOURS, ", ".join(f"{d} ({h}h)" for d, h in dropped)))

    fig, axes = plt.subplots(4, 1, figsize=(11.5, 13.5), sharex=True,
                             gridspec_kw=dict(hspace=0.24, left=0.09, right=0.83,
                                              top=0.91, bottom=0.055))
    fig.patch.set_facecolor(c["surface"])

    def per_msg(addr_key, msg_key):
        """Mean addresses per message. NaN on a zero-message day so the line
        breaks rather than dropping to 0 on the log axis."""
        return [a / m if m else float("nan")
                for a, m in zip(g(addr_key), g(msg_key))]

    panels = [
        ("Messages received per day", "messages", True,
         [("Gossip  (unsolicited)", g("g_msgs"), c["gossip"]),
          ("Getaddr (reply to our GETADDR)", g("ga_msgs"), c["getaddr"])]),
        ("Addresses received per day", "addresses", False,
         [("Gossip", g("g_addrs"), c["gossip"]),
          ("Getaddr", g("ga_addrs"), c["getaddr"])]),
        # The derived panel: where the 2026-07-15 break is starkest. Gossip is
        # pinned near 2-3 by the relay gate (size <= 10), so any movement here is
        # the getaddr line -- and it jumps ~16 -> ~133 overnight as the 11-989
        # band vanishes and only full 1000-address dumps remain.
        ("Average addresses per message", "addresses / message", True,
         [("Gossip", per_msg("g_addrs", "g_msgs"), c["gossip"]),
          ("Getaddr", per_msg("ga_addrs", "ga_msgs"), c["getaddr"])]),
        ("Addresses rate-limited per day  (dropped before addrman)", "addresses", False,
         [("Gossip", g("g_rl"), c["gossip"]),
          ("Getaddr", g("ga_rl"), c["getaddr"])]),
    ]

    for ax, (title, ylab, logy, series) in zip(axes, panels):
        ax.set_facecolor(c["surface"])
        # shade partial days first so marks sit on top. These are days the node
        # was not up for the full 24 h -- without an obvious band, a short bar
        # reads as a real collapse (control's Jul 24 holds ~1 h of data).
        for d, xd in zip(days, x):
            if d in partial:
                ax.axvspan(xd - datetime.timedelta(hours=12),
                           xd + datetime.timedelta(hours=12),
                           facecolor=c["band"], edgecolor=c["ink3"], lw=0.4,
                           hatch="///", alpha=0.85, zorder=0)
        for label, ys, colr in series:
            ax.plot(x, ys, "-o", color=colr, lw=2, ms=4.5,
                    mec=c["surface"], mew=1.2, zorder=3, label=label,
                    clip_on=False)

        # Direct labels at the right edge (2 series -> always direct-labelled).
        # Nudge apart when the final values nearly coincide, else they overprint
        # -- which is exactly what happens in the rate-limited panel, where both
        # series land near zero.
        ends = sorted(((s[1][-1], s[0].split()[0], s[2]) for s in series),
                      reverse=True)
        # measure the gap in PIXELS so this works on the log panel too
        fig.canvas.draw()
        py = [ax.transData.transform((0, max(v, 1e-9)))[1] for v, _, _ in ends]
        close = abs(py[0] - py[-1]) < 14
        for i, (val, name, colr) in enumerate(ends):
            dy = 0 if not close else (7 if i == 0 else -7)
            ax.annotate(name, (x[-1], val), xytext=(9, dy),
                        textcoords="offset points", va="center", ha="left",
                        fontsize=9.5, color=colr, annotation_clip=False)
        if logy:
            ax.set_yscale("log")
            ax.set_ylabel(ylab + "  (log scale)", color=c["ink2"], fontsize=10)
        else:
            ax.set_ylim(bottom=0)
            ax.set_ylabel(ylab, color=c["ink2"], fontsize=10)
        ax.set_title(title, color=c["ink"], fontsize=11.5, loc="left", pad=8)
        ax.yaxis.set_major_formatter(FuncFormatter(thousands))
        ax.grid(True, axis="y", color=c["grid"], lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(c["grid"])
        ax.tick_params(colors=c["ink2"], labelsize=9, length=0)

    axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    for lbl in axes[-1].get_xticklabels():
        lbl.set_rotation(45); lbl.set_ha("right")

    fig.suptitle(f"addr channel volume by day — {TITLE[node]}",
                 color=c["ink"], fontsize=14, x=0.09, ha="left", y=0.982)
    # two lines: the one-liner clipped the right edge once the drop note appeared
    fig.text(0.09, 0.958,
             f"{days[0]} → {days[-1]}  ·  counted from “Received addr:” log line"
             f"  ·  getaddr = reply to a GETADDR we sent that peer; gossip = all else",
             color=c["ink3"], fontsize=9, ha="left")
    fig.text(0.09, 0.941,
             "shaded = partial day (node up <24 h)"
             + ("".join(f"  ·  {d} dropped, only {h} h of log"
                        for d, h in dropped) if dropped else ""),
             color=c["ink3"], fontsize=9, ha="left")

    axes[0].legend(loc="upper left", frameon=False, fontsize=9.5,
                   labelcolor=c["ink2"], handlelength=1.6, ncol=2)

    out = out or f"{HERE}/addr_channels_{node}{'_dark' if dark else ''}.png"
    fig.savefig(out, dpi=150, facecolor=c["surface"])
    print("wrote", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    node = next((v for v in a if v in ("test", "control")), "test")
    out = a[a.index("-o") + 1] if "-o" in a else None
    main(node, "--dark" in a, out)
