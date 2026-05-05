"""quick_reachability.py — test if peers are responding to Bitcoin handshake"""
import asyncio
import socket
import struct
import time

async def is_bitcoin_node(ip: str, port: int, timeout=5.0):
    """Send a Bitcoin version message and check for a reply."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout
        )
    except (asyncio.TimeoutError, OSError):
        return False, "connect_failed"

    try:
        # Construct a minimal Bitcoin version message
        magic = b'\xf9\xbe\xb4\xd9'  # mainnet
        command = b'version' + b'\x00' * 5
        payload = (
            struct.pack('<I', 70016) +              # version
            struct.pack('<Q', 0) +                  # services
            struct.pack('<q', int(time.time())) +   # timestamp
            b'\x00' * 26 +                          # addr_recv
            b'\x00' * 26 +                          # addr_from
            struct.pack('<Q', 0) +                  # nonce
            b'\x00' +                               # user agent length 0
            struct.pack('<I', 0) +                  # start_height
            b'\x00'                                 # relay
        )
        checksum = b'\x5d\xf6\xe0\xe2'  # double SHA256 of empty payload, then [:4]
        # We need real checksum for the actual payload — skipping for simplicity,
        # most nodes accept the connection without strict validation
        from hashlib import sha256
        checksum = sha256(sha256(payload).digest()).digest()[:4]
        header = magic + command + struct.pack('<I', len(payload)) + checksum
        writer.write(header + payload)
        await writer.drain()

        # Read at least 24 bytes (header) — that's enough to confirm a response
        data = await asyncio.wait_for(reader.read(24), timeout=timeout)
        result = (len(data) >= 24 and data[:4] == magic, "got_response" if data else "no_response")
    except (asyncio.TimeoutError, OSError, ConnectionResetError) as e:
        result = (False, f"error_{type(e).__name__}")
    finally:
        writer.close()
        try: await writer.wait_closed()
        except: pass

    return result

async def check_peers(filename):
    with open(filename) as f:
        peers = [line.strip() for line in f if line.strip()]

    reachable = 0
    for peer in peers:
        ip, port = peer.rsplit(':', 1)
        ok, reason = await is_bitcoin_node(ip, int(port))
        status = "REACHABLE" if ok else f"unreachable ({reason})"
        print(f"{peer:50s} {status}")
        if ok: reachable += 1
    print(f"\n{reachable}/{len(peers)} reachable")

if __name__ == "__main__":
    asyncio.run(check_peers("apollo_peers.txt"))