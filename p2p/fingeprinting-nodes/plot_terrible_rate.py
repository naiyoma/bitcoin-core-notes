#!/usr/bin/env python3
"""Terrible-address rate over time: normal (control) vs test node."""
from datetime import date
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CONTROL = "#1f77b4"   # blue  -> normal node
TEST    = "#d62728"   # red   -> test node

dates   = [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 11),
           date(2026, 6, 26), date(2026, 7, 2)]
control = [0.12, 0.15, 0.13, 0.51, 1.01]
test    = [5.34, 4.41, 4.06, 3.12, 2.23]

fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(dates, test,    "o-", color=TEST,    lw=2.2, ms=7, label="Test node (getaddr forced 30d old)")
ax.plot(dates, control, "o-", color=CONTROL, lw=2.2, ms=7, label="Normal node (control)")

for x, y in zip(dates, test):
    ax.annotate(f"{y:.2f}%", (x, y), textcoords="offset points", xytext=(0, 9),
                ha="center", fontsize=9, color=TEST)
for x, y in zip(dates, control):
    ax.annotate(f"{y:.2f}%", (x, y), textcoords="offset points", xytext=(0, -15),
                ha="center", fontsize=9, color=CONTROL)

ax.set_title("Terrible-address rate over time — normal vs test node", fontsize=14)
ax.set_xlabel("Date")
ax.set_ylabel("Terrible addresses (% of addrman > 30 days)")
ax.set_ylim(-0.3, 6)
ax.legend(loc="center right", fontsize=10)
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.annotate("test is force-fed 30-day-old addresses the whole time,\n"
            "yet its terrible rate falls while the control's rises",
            (date(2026, 6, 14), 5.2), fontsize=9, color="#555")

fig.autofmt_xdate()
fig.tight_layout()
out = "terrible_rate_comparison.png"
fig.savefig(out, dpi=120, bbox_inches="tight")
print("wrote", out)
