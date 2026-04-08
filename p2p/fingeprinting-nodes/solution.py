import hashlib

SECRET = b"my_node_secret"
BUCKET = 6 * 3600    # 6 hours in seconds
ONE_DAY = 86400      # 1 day in seconds

def transform(address, peer_id, real_timestamp, now=0):
    # Step 1: h = H(addr, peer, secret)
    data = address.encode() + peer_id.encode() + SECRET
    h    = hashlib.sha256(data).digest()
    val1 = int.from_bytes(h[:4], "big")   # for range
    val2 = int.from_bytes(h[4:8], "big")  # for delta

    # Step 2: range = 3d + (h % 2d)  →  range ∈ [3d, 5d]
    range_s = 3 * ONE_DAY + (val1 % (2 * ONE_DAY))

    # Step 3: window = range + 1d
    window_s = range_s + ONE_DAY

    # Step 4: Δ = (h % window) - range  →  Δ ∈ [-range, +1d]
    delta = (val2 % window_s) - range_s

    # Step 5: t' = real_timestamp + Δ
    t_prime = real_timestamp + delta

    # Step 6: t_final = floor(t' / BUCKET) * BUCKET
    t_final = (t_prime // BUCKET) * BUCKET

    return t_final, delta, range_s


now = 0
peers = [
    ("IPv4  network", "network_key_0x1111111111111111"),
    ("Tor   network", "network_key_0x9999999999999999"),
    ("I2P   network", "network_key_0xAAAAAAAAAAAAAAAA"),
]
addresses = ["xyz.onion", "abc.onion", "1.2.3.4", "5.6.7.8", "def.onion"]

for addr in addresses:
    real_timestamp = now - 10 * ONE_DAY
    print(f"addr = {addr}  (real age = 10.00 days)")
    for name, peer_id in peers:
        t_final, delta, range_s = transform(addr, peer_id, real_timestamp, now)
        age_final = (now - t_final) / ONE_DAY
        delta_h   = delta / 3600
        range_d   = range_s / ONE_DAY
        print(f"  {name}: range=±{range_d:.1f}d  Δ={delta_h:+.1f}h -> {age_final:.2f} days")
    print()