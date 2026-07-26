#!/usr/bin/env python3
"""
Normal vs Experiment node comparison — 3 panels:
  1. Terrible address rate over time (% of total addrs)
  2. getaddr share of addr-related messages (getaddr / (getaddr+gossip) messages)
  3. getaddr share of delivered addresses (getaddr / (getaddr+gossip) addrs)

Choices (data was ambiguous):
  - Jun 9 has two readings per node; the later 9pm snapshot is used.
  - The date=2026-06-20 block had no node label / no terrible count -> omitted.
"""
from datetime import date
import matplotlib.pyplot as plt

NORMAL = "tab:blue"
EXPERIMENT = "crimson"

# ---------------------------------------------------------------- data --------
# Each record: date, terrible_pct, msg_getaddr, msg_gossip, addr_getaddr, addr_gossip
# addr_* is None where no delivered-address breakdown was reported that day.
normal = [
    dict(d=date(2026, 6, 8),  terrible=0.12, mg=6,  mgo=5644, ag=None,  ago=None),
    dict(d=date(2026, 6, 9),  terrible=0.15, mg=22, mgo=5125, ag=22000, ago=14878),  # 9pm
    dict(d=date(2026, 6, 11), terrible=0.13, mg=1,  mgo=4942, ag=1000,  ago=14065),
    dict(d=date(2026, 6, 26), terrible=0.51, mg=5,  mgo=6978, ag=5000,  ago=18541),
    dict(d=date(2026, 7, 2),  terrible=1.01, mg=5,  mgo=6561, ag=5000,  ago=18245),
]
experiment = [
    dict(d=date(2026, 6, 8),  terrible=5.34, mg=8,  mgo=52,   ag=None,  ago=None),
    dict(d=date(2026, 6, 9),  terrible=4.41, mg=12, mgo=9391, ag=12000, ago=24870),  # 9pm
    dict(d=date(2026, 6, 11), terrible=4.06, mg=2,  mgo=5005, ag=2000,  ago=14796),
    dict(d=date(2026, 6, 26), terrible=3.12, mg=7,  mgo=6,    ag=6999,  ago=9),
    dict(d=date(2026, 7, 2),  terrible=2.23, mg=7,  mgo=9829, ag=7000,  ago=29772),
]


def msg_getaddr_pct(r):
    tot = r["mg"] + r["mgo"]
    return 100.0 * r["mg"] / tot if tot else None


def addr_getaddr_pct(r):
    if r["ag"] is None:
        return None
    tot = r["ag"] + r["ago"]
    return 100.0 * r["ag"] / tot if tot else None


def series(recs, fn):
    xs, ys = [], []
    for r in recs:
        v = fn(r)
        if v is not None:
            xs.append(r["d"])
            ys.append(v)
    return xs, ys


# ---------------------------------------------------------------- plot ---------
fig, axes = plt.subplots(1, 3, figsize=(21, 6))
fig.suptitle("Normal vs Experiment Node — address quality & getaddr usage",
             fontsize=17, y=1.02)


def annotate(ax, xs, ys, color, fmt="{:.2f}%", dy=8):
    for x, y in zip(xs, ys):
        ax.annotate(fmt.format(y), (x, y), textcoords="offset points",
                    xytext=(0, dy), ha="center", fontsize=8, color=color)


# --- Panel 1: terrible address rate ---------------------------------------
ax = axes[0]
nx, ny = series(normal, lambda r: r["terrible"])
ex, ey = series(experiment, lambda r: r["terrible"])
ax.plot(nx, ny, "o-", color=NORMAL, label="Normal node")
ax.plot(ex, ey, "o-", color=EXPERIMENT, label="Experiment node")
annotate(ax, nx, ny, NORMAL)
annotate(ax, ex, ey, EXPERIMENT)
ax.set_title("Terrible address rate over time")
ax.set_xlabel("Date")
ax.set_ylabel("Terrible addresses (% of total)")
ax.legend()
ax.grid(True, alpha=0.3)

# --- Panel 2: getaddr share of messages -----------------------------------
ax = axes[1]
nx, ny = series(normal, msg_getaddr_pct)
ex, ey = series(experiment, msg_getaddr_pct)
ax.plot(nx, ny, "s-", color=NORMAL, label="Normal node")
ax.plot(ex, ey, "s-", color=EXPERIMENT, label="Experiment node")
annotate(ax, nx, ny, NORMAL, fmt="{:.2f}%")
annotate(ax, ex, ey, EXPERIMENT, fmt="{:.1f}%")
ax.set_title("getaddr share of addr-related messages")
ax.set_xlabel("Date")
ax.set_ylabel("getaddr messages (% of addr messages)")
ax.legend()
ax.grid(True, alpha=0.3)

# --- Panel 3: getaddr share of delivered addresses ------------------------
ax = axes[2]
nx, ny = series(normal, addr_getaddr_pct)
ex, ey = series(experiment, addr_getaddr_pct)
ax.plot(nx, ny, "^-", color=NORMAL, label="Normal node")
ax.plot(ex, ey, "^-", color=EXPERIMENT, label="Experiment node")
annotate(ax, nx, ny, NORMAL, fmt="{:.1f}%")
annotate(ax, ex, ey, EXPERIMENT, fmt="{:.1f}%")
ax.set_title("getaddr share of delivered addresses")
ax.set_xlabel("Date")
ax.set_ylabel("Addresses from getaddr (% of delivered)")
ax.legend()
ax.grid(True, alpha=0.3)

fig.autofmt_xdate()
fig.tight_layout()
out = "node_comparison_3panel.png"
fig.savefig(out, dpi=100, bbox_inches="tight")
print("wrote", out)
