import hashlib
import time

SECRET = b"my_node_secret"
MAX_OFFSET = 24 * 60 * 60
BUCKET = 6 * 60 * 60



#Derministic offset function
# what does a determistic offset mean ?

def deterministic_offset(address: str, peer_id: str) -> int:
    """
    Returns Δ in range [-MAX_OFFSET, +MAX_OFFSET]
    Deterministic per (address, peer)
    """
    data = address.encode() + peer_id.encode() + SECRET
    h = hashlib.sha256(data).digest()

    # the first thing is encode the address and the peer id and then the secret
    #and then i hash this data using sha256

    # then i convert this to be 8 bytes of an int
    val = int.from_bytes(h[:8], "big")


    #map to the range [-MAX_OFFSET, +MAX_OFFSET]
    return (val % ( 2 * MAX_OFFSET)) - MAX_OFFSET

#QUANTINAZATION function
# what is bucketing an quantinization

def quantinize(timestamp:int ) -> int:
    """
    Quantinizes timestamp to the nearest bucket
    """
    return (timestamp // BUCKET) * BUCKET

# apply transform function
def transform(addresses, peer_id):
    transformed = []

    for addr, t in addresses:
        delta = deterministic_offset(addr, peer_id)
        t_shifted = t + delta
        t_final = quantinize(t_shifted)

        transformed.append((addr, t, delta, t_final))

    return transformed


#example data
now = int(time.time())
addresses = [
    ("addr_B", now - 1 * 86400), 
    ("addr_C", now - 6 * 86400), 
    ("addr_D", now - 5 * 86400),
]

#simulate two peers
ipv4_view = transform(addresses, peer_id="ipv4_peer")
tor_view = transform(addresses, peer_id="tor_peer")

def print_view(name, view):
    print(f"\n{name}")
    print("-" * 50)
    for addr, original, delta, final in view:
        age_orig = (now - original) / 86400
        age_final = (now - final) / 86400
        print(f"{addr}: oriignal={age_orig:2f}d, Δ={delta/3600:.1f}h, final={age_final:.2f}d")

print_view("IPV4 VIEW", ipv4_view)
print_view("TOR_VIEW", tor_view)


