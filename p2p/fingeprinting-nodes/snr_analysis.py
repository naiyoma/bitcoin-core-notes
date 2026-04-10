#!/usr/bin/env python3
import json, time, hashlib, random, math

SECRET = b"my_node_secret"

def deterministic_offset(address, peer_id, max_offset):
    data = address.encode() + peer_id.encode() + SECRET
    h = hashlib.sha256(data).digest()
    val = int.from_bytes(h[:8], "big")
    return (val % (2 * max_offset)) - max_offset

def quantize(timestamp, bucket=6*3600):
    return round(timestamp / bucket) * bucket

with open("addrman_timestamps.json") as f:
    all_timestamps = json.load(f)

now = int(time.time())
sample = random.sample(all_timestamps, min(189, len(all_timestamps)))
addresses = [f"addr_{i}" for i in range(len(sample))]

print(f"{'MAX_OFFSET':>14} {'True matches':>14} {'False matches':>15} {'SNR':>8} {'Attack?':>12}")
print("-" * 70)

for max_offset_h in [24, 48, 72, 120, 168, 240, 360]:
    max_offset_s = max_offset_h * 3600

    ipv4_view = {a: quantize(t + deterministic_offset(a, "ipv4", max_offset_s))
                 for a, t in zip(addresses, sample)}
    tor_view  = {a: quantize(t + deterministic_offset(a, "tor",  max_offset_s))
                 for a, t in zip(addresses, sample)}

    true_matches  = sum(1 for a in addresses
                        if abs(ipv4_view[a] - tor_view[a]) <= max_offset_s)
    p_false       = min(1.0, (2 * max_offset_s) / (30 * 86400))
    false_matches = len(addresses) * p_false
    snr           = true_matches / false_matches if false_matches > 0 else float("inf")
    attack        = "YES" if snr > 3 else ("MARGINAL" if snr > 1.5 else "NO")

    print(f"±{max_offset_h:>5}h ({max_offset_h//24:>2}d)  "
          f"{true_matches:>12}  "
          f"{false_matches:>13.1f}  "
          f"{snr:>6.1f}x  "
          f"{attack:>12}")