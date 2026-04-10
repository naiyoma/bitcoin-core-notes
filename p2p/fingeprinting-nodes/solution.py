# import hashlib

# SECRET = b"my_node_secret"
# BUCKET = 6 * 3600    # 6 hours in seconds
# ONE_DAY = 86400      # 1 day in seconds

# def transform(address, peer_id, real_timestamp, now=0):
#     # Step 1: h = H(addr, peer, secret)
#     data = address.encode() + peer_id.encode() + SECRET
#     h    = hashlib.sha256(data).digest()
#     val1 = int.from_bytes(h[:4], "big")   # for range
#     val2 = int.from_bytes(h[4:8], "big")  # for delta

#     # Step 2: range = 3d + (h % 2d)  →  range ∈ [3d, 5d]
#     range_s = 3 * ONE_DAY + (val1 % (2 * ONE_DAY))

#     # Step 3: window = range + 1d
#     window_s = range_s + ONE_DAY

#     # Step 4: Δ = (h % window) - range  →  Δ ∈ [-range, +1d]
#     delta = (val2 % window_s) - range_s

#     # Step 5: t' = real_timestamp + Δ
#     t_prime = real_timestamp + delta

#     # Step 6: t_final = floor(t' / BUCKET) * BUCKET
#     t_final = (t_prime // BUCKET) * BUCKET

#     return t_final, delta, range_s


# now = 0
# peers = [
#     ("IPv4  network", "network_key_0x1111111111111111"),
#     ("Tor   network", "network_key_0x9999999999999999"),
#     ("I2P   network", "network_key_0xAAAAAAAAAAAAAAAA"),
# ]
# addresses = ["xyz.onion", "abc.onion", "1.2.3.4", "5.6.7.8", "def.onion"]

# for addr in addresses:
#     real_timestamp = now - 10 * ONE_DAY
#     print(f"addr = {addr}  (real age = 10.00 days)")
#     for name, peer_id in peers:
#         t_final, delta, range_s = transform(addr, peer_id, real_timestamp, now)
#         age_final = (now - t_final) / ONE_DAY
#         delta_h   = delta / 3600
#         range_d   = range_s / ONE_DAY
#         print(f"  {name}: range=±{range_d:.1f}d  Δ={delta_h:+.1f}h -> {age_final:.2f} days")
#     print()



import hashlib
import random

SECRET = b"my_node_secret"
BUCKET = 6 * 3600
ONE_DAY = 86400
REAL_AGE_DAYS = 25
NUM_QUERIES = 50

def deterministic_offset(address, peer_id):
    data = address.encode() + peer_id.encode() + SECRET
    h = hashlib.sha256(data).digest()
    val1 = int.from_bytes(h[:4], "big")
    val2 = int.from_bytes(h[4:8], "big")
    range_s = 3 * ONE_DAY + (val1 % (2 * ONE_DAY))
    window_s = range_s + ONE_DAY
    delta = (val2 % window_s) - range_s
    return delta, range_s

def quantize(timestamp):
    return (timestamp // BUCKET) * BUCKET

now = 0
real_timestamp = now - REAL_AGE_DAYS * ONE_DAY
addr = "xyz.onion"

print("=" * 60)
print(f"Real age: {REAL_AGE_DAYS} days")
print(f"Number of queries: {NUM_QUERIES}")
print("=" * 60)

# ─────────────────────────────────────────
# SIMPLE FUZZING
# ─────────────────────────────────────────
print("\nSIMPLE FUZZING ±5 days")
print("-" * 60)

fuzz_range = 5 * ONE_DAY
samples = []
for i in range(NUM_QUERIES):
    noise = random.randint(-fuzz_range, fuzz_range)
    t_fuzzed = quantize(real_timestamp + noise)
    age = (now - t_fuzzed) / ONE_DAY
    samples.append(age)
    if i < 5:
        print(f"  Query {i+1}: {REAL_AGE_DAYS}d + random = {age:.2f}d")

print(f"  ...")
average = sum(samples) / len(samples)
error = abs(average - REAL_AGE_DAYS)
print(f"\n  Average after {NUM_QUERIES} queries: {average:.2f}d")
print(f"  Error from real age:            ±{error:.2f}d")
print(f"  Real timestamp recovered?       {'YES ✗' if error < 1 else 'NO ✓'}")

# ─────────────────────────────────────────
# DETERMINISTIC DISTORTION
# ─────────────────────────────────────────
print("\nDETERMINISTIC DISTORTION")
print("-" * 60)

peer_samples = []
for i in range(NUM_QUERIES):
    peer_id = f"network_key_peer_{i:04d}"
    delta, range_s = deterministic_offset(addr, peer_id)
    t_distorted = quantize(real_timestamp + delta)
    age = (now - t_distorted) / ONE_DAY
    peer_samples.append(age)
    if i < 5:
        delta_h = delta / 3600
        range_d = range_s / ONE_DAY
        print(f"  Peer {i+1}: {REAL_AGE_DAYS}d + H(addr,peer,secret) ="
              f" always {age:.2f}d  (Δ={delta_h:+.1f}h, range=±{range_d:.1f}d)")

print(f"  ...")
average_det = sum(peer_samples) / len(peer_samples)
error_det = abs(average_det - REAL_AGE_DAYS)
print(f"\n  Average after {NUM_QUERIES} queries: {average_det:.2f}d")
print(f"  Error from real age:            ±{error_det:.2f}d")
print(f"  Real timestamp recovered?       {'YES ✗' if error_det < 1 else 'NO ✓'}")

# ─────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Real age:                     {REAL_AGE_DAYS} days")
print(f"  Simple fuzzing average:       {sum(samples)/len(samples):.2f}d"
      f"  (error ±{abs(sum(samples)/len(samples)-REAL_AGE_DAYS):.2f}d)")
print(f"  Deterministic average:        {sum(peer_samples)/len(peer_samples):.2f}d"
      f"  (error ±{abs(sum(peer_samples)/len(peer_samples)-REAL_AGE_DAYS):.2f}d)")
print()
print("  Simple fuzzing:      attacker averages → recovers real timestamp ✗")
print("  Deterministic:       attacker averages → gets wrong value ✓")