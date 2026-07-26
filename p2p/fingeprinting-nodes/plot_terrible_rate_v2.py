#!/usr/bin/env python3
"""
Terrible-address rate over time — test vs control, with outages made explicit.

Supersedes plot_terrible_rate.py, which stopped at 2026-07-02 and drew every
segment the same way. Two things changed:

  * the series now runs to 2026-07-24 (adds the Jul 17 readings and the hourly
    cron snapshots), and
  * segments that SPAN AN OUTAGE are dashed and the dead time is shaded.

That second point is not cosmetic. While a node is down, wall-clock keeps
advancing but no gossip arrives, so entries age past ADDRMAN_HORIZON and the
rate climbs on its own. The test node's 0.92% -> 5.23% jump is almost entirely
its 92-hour outage, not a reversal of the experiment's result; drawn as a plain
solid line it reads as the opposite of what happened.

usage: plot_terrible_rate_v2.py [--dark] [-o out.png]
"""
import sys, json, datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = "/home/ubuntu/Projects/bitcoin-core-notes/p2p/fingeprinting-nodes"

# Validated categorical slots 1 & 2 (dataviz references/palette.md):
#   node validate_palette.js "#2a78d6,#eb6834" --mode light -> ALL PASS
#   node validate_palette.js "#3987e5,#d95926" --mode dark  -> ALL PASS
THEME = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", ink3="#8a8880",
                  grid="#e4e3df", band="#dedcd5", control="#2a78d6", test="#eb6834"),
    "dark":  dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", ink3="#83817a",
                  grid="#2f2f2d", band="#333330", control="#3987e5", test="#d95926"),
}

LABEL = {"control": "Control node (unmodified)",
         "test": "Test node (getaddr forced 30 d old)"}


def parse(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main(dark=False, out=None):
    c = THEME["dark" if dark else "light"]
    data = json.load(open(f"{HERE}/terrible_rate_series.json"))

    fig, ax = plt.subplots(figsize=(12, 6.6))
    fig.patch.set_facecolor(c["surface"])
    ax.set_facecolor(c["surface"])
    fig.subplots_adjust(left=0.135, right=0.80, top=0.85, bottom=0.13)

    # shade every known outage, both nodes, behind the marks
    for node, spans in data["outages"].items():
        for a, b in spans:
            ax.axvspan(parse(a), parse(b), facecolor=c["band"],
                       edgecolor=c["ink3"], lw=0.4, hatch="///",
                       alpha=0.8, zorder=0)

    for node in ("control", "test"):
        pts = sorted(data["readings"][node], key=lambda r: r["t"])
        xs = [parse(r["t"]) for r in pts]
        ys = [r["rate"] for r in pts]
        spans = [(parse(a), parse(b)) for a, b in data["outages"].get(node, [])]

        # draw segment by segment: dashed if this gap contains dead time, so a
        # rise caused by the node being off is never read as behaviour
        for i in range(len(xs) - 1):
            crosses = any(a < xs[i + 1] and b > xs[i] for a, b in spans)
            style = {"dashes": (4, 3)} if crosses else {"ls": "-"}
            ax.plot(xs[i:i + 2], ys[i:i + 2], color=c[node], lw=2, zorder=2,
                    **style)
        ax.plot(xs, ys, "o", color=c[node], ms=6.5, mec=c["surface"], mew=1.4,
                zorder=3, label=LABEL[node])
        # Value labels on the first and last reading only -- never every point.
        # First goes to the LEFT of its marker (below it would collide with the
        # x-axis at 0.12%), last sits under the series name at the right edge.
        ax.annotate(f"{node.capitalize()}   {ys[-1]:.2f}%", (xs[-1], ys[-1]),
                    xytext=(11, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=10, color=c[node],
                    annotation_clip=False)
        ax.annotate(f"{ys[0]:.2f}%  ", (xs[0], ys[0]), xytext=(-9, 0),
                    textcoords="offset points", va="center", ha="right",
                    fontsize=9.5, color=c[node], annotation_clip=False)

    ax.set_ylim(0, 6.2)
    ax.set_ylabel("terrible addresses  (% of addrman, nTime older than 30 d)",
                  color=c["ink2"], fontsize=10)
    ax.grid(True, axis="y", color=c["grid"], lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(c["grid"])
    ax.tick_params(colors=c["ink2"], labelsize=9, length=0)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    for lbl in ax.get_xticklabels():
        lbl.set_rotation(45); lbl.set_ha("right")

    ax.set_title("Terrible-address rate over time — test vs control",
                 color=c["ink"], fontsize=14, loc="left", pad=26)
    fig.text(0.135, 0.885,
             "shaded / dashed = node was down; the rate climbs there on ageing "
             "alone, with no gossip arriving to refresh anything",
             color=c["ink3"], fontsize=9.5, ha="left")

    ax.legend(loc="upper center", frameon=False, fontsize=9.5,
              labelcolor=c["ink2"], handlelength=1.6)

    out = out or f"{HERE}/terrible_rate_v2{'_dark' if dark else ''}.png"
    fig.savefig(out, dpi=150, facecolor=c["surface"])
    print("wrote", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    main("--dark" in a, a[a.index("-o") + 1] if "-o" in a else None)
