#!/usr/bin/env python3
"""
self-announcement / addr-relay / getaddr interaction — evidence figure.

Built from a full single-pass parse of both nodes' debug.log (see
logparse_control.json / logparse_test.json, produced by parse_addr_logs.py) plus
the point-in-time getrawaddrman "terrible rate" readings.

Control node  (170.75.165.140 "normanode"): observation-only, no timestamp forcing.
Test node     (170.75.164.168 "test"):       getaddr responses (>=990 addr msgs)
                                              forced to 30 days old on arrival.

Channel split uses the experiment's own >=990 heuristic already baked into the
log lines: a >=990-addr message is a bulk getaddr reply; anything smaller is
gossip (relayed addr + peer self-announcements).
"""
import json
from datetime import date, datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CONTROL = "#1f77b4"   # tab:blue  -> control / normal node
TEST    = "#d62728"   # red       -> test / experiment node
GETADDR = "#c25e00"   # amber     -> getaddr channel (bulk, old/forced)
GOSSIP  = "#2a9d5c"   # green     -> gossip / self-announce channel (fresh)

def load_daily(path):
    d = json.load(open(path))["daily"]
    xs, ga, go, share = [], [], [], []
    for day in sorted(d):
        b = d[day]
        tot = b["ga_addrs"] + b["go_addrs"]
        xs.append(datetime.strptime(day, "%Y-%m-%d"))
        ga.append(b["ga_addrs"]); go.append(b["go_addrs"])
        share.append(100 * b["ga_addrs"] / tot if tot else 0)
    return xs, ga, go, share

cx, cga, cgo, cshare = load_daily("logparse_control.json")
tx, tga, tgo, tshare = load_daily("logparse_test.json")

# point-in-time "terrible" (>30-day) rate, % of addrman (hand readings + today)
terr_dates = [date(2026,6,8), date(2026,6,9), date(2026,6,11),
              date(2026,6,26), date(2026,7,2), date(2026,7,17)]
terr_control = [0.12, 0.15, 0.13, 0.51, 1.01, 1.72]
terr_test    = [5.34, 4.41, 4.06, 3.12, 2.23, 0.92]

def gossip_hist(path, cap=25):
    h = json.load(open(path))["gossip_size_hist"]
    xs = list(range(1, cap + 1))
    ys = [h.get(str(s), 0) for s in xs]
    return xs, ys
csz_x, csz_y = gossip_hist("logparse_control.json")

fig, axes = plt.subplots(2, 2, figsize=(15, 10))
fig.suptitle("Self-announcement / addr-relay / getaddr — who keeps the addrman fresh?",
             fontsize=16, y=0.995)

# ---- Panel A: outcome — terrible rate over time -------------------------------
ax = axes[0][0]
ax.plot(terr_dates, terr_control, "o-", color=CONTROL, lw=2, label="Control (normal)")
ax.plot(terr_dates, terr_test,    "o-", color=TEST,    lw=2, label="Test (getaddr forced 30d old)")
for x, y in zip(terr_dates, terr_test):
    ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(0, 7),
                ha="center", fontsize=8, color=TEST)
for x, y in zip(terr_dates, terr_control):
    ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(0, -12),
                ha="center", fontsize=8, color=CONTROL)
ax.set_title("A · Addrman 'terrible' rate (>30-day addresses)")
ax.set_ylabel("% of addrman that is terrible")
ax.annotate("test starts poisoned by forced getaddr,\n"
            "then gossip heals it BELOW control",
            (date(2026,6,20), 4.6), fontsize=8.5, color="#555")
ax.legend(loc="upper right", fontsize=9)
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

# ---- Panel B: test node daily inflow by channel (the mechanism) ---------------
ax = axes[0][1]
ax.stackplot(tx, tgo, tga, colors=[GOSSIP, GETADDR], alpha=0.85,
             labels=["gossip / self-announce (fresh)",
                     "getaddr reply (forced 30d old = terrible)"])
ax.set_title("B · Test node: addresses received per day, by channel")
ax.set_ylabel("addresses / day")
ax.legend(loc="upper left", fontsize=9)
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.annotate("every one of these is poisoned\nyet freshness still improves",
            (datetime(2026,7,6), 60000), fontsize=8.5, color="#7a3b00")

# ---- Panel C: getaddr share of delivered addresses, per day -------------------
ax = axes[1][0]
ax.plot(cx, cshare, "-", color=CONTROL, lw=1.6, label="Control")
ax.plot(tx, tshare, "-", color=TEST,    lw=1.6, label="Test")
ax.axhline(50, color="#999", ls="--", lw=1)
ax.set_title("C · getaddr share of delivered addresses (per day)")
ax.set_ylabel("% of received addresses from getaddr")
ax.set_ylim(0, 60)
ax.legend(loc="upper right", fontsize=9)
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.annotate("gossip supplies the majority\nof addresses almost every day",
            (datetime(2026,7,2), 5), fontsize=8.5, color="#555")

# ---- Panel D: gossip message size = self-announcement signature ---------------
ax = axes[1][1]
ax.bar(csz_x, csz_y, color=GOSSIP, width=0.85)
ax.set_yscale("log")
ax.set_title("D · Gossip message size distribution (control node)")
ax.set_xlabel("addresses per gossip message")
ax.set_ylabel("message count (log)")
ax.grid(True, alpha=0.3, which="both")
tot = sum(csz_y)
ax.annotate(f"size=1 is {100*csz_y[0]/tot:.0f}% of gossip msgs\n"
            "(peer self-announcements +\nsingle-address relays)",
            (6, csz_y[0]*0.5), fontsize=8.5, color="#1c6b3f")

fig.tight_layout(rect=[0, 0, 1, 0.98])
out = "self_announce_getaddr.png"
fig.savefig(out, dpi=110, bbox_inches="tight")
print("wrote", out)
