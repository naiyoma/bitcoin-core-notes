import struct, shutil, time
from pathlib import Path

PEERS_DAT = Path.home() / '.bitcoin' / 'peers.dat'
shutil.copy(PEERS_DAT, str(PEERS_DAT) + '.bak2')
print(f"Backup saved to {PEERS_DAT}.bak2")

data = bytearray(PEERS_DAT.read_bytes())
now = int(time.time())
old_ts = now - (31 * 86400)

two_years_ago = now - (2 * 365 * 86400)
patched = 0
i = 0
while i <= len(data) - 4:
    val = struct.unpack_from('<I', data, i)[0]
    if two_years_ago < val < now:
        struct.pack_into('<I', data, i, old_ts)
        patched += 1
        i += 4
    else:
        i += 1

print(f"Patched {patched} timestamps")
PEERS_DAT.write_bytes(data)
print("Done.")
