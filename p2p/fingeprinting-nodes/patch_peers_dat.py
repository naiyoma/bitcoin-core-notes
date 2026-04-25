#!/usr/bin/env python3
"""
Read an existing peers.dat, change every address's nTime to 31 days ago
(making all entries "terrible" per AddrInfo::IsTerrible), and write it back
with a correct checksum.

Usage:
    python3 patch_peers_dat.py <path/to/peers.dat> [days_old]

    days_old defaults to 31.

Works with both old (format 1/2, V1_DISK) and new (format 3/4, V2_DISK/BIP155)
peers.dat files.  The bucket table and asmap version are left untouched.
"""

import hashlib
import io
import struct
import sys
import time


# ── Format constants (mirror addrman_impl.h / protocol.h) ─────────────────────
FORMAT_V1_DETERMINISTIC = 1
FORMAT_V2_ASMAP         = 2
FORMAT_V3_BIP155        = 3   # entries switch to BIP155 (V2_DISK) encoding
FORMAT_V4_MULTIPORT     = 4

ADDRMAN_NEW_BUCKET_COUNT = 1 << 10   # 1024

DISK_VERSION_IGNORE_MASK = (1 << 19) - 1   # low 19 bits are ignored


# ── Low-level read helpers ─────────────────────────────────────────────────────

def read_compact_size(f):
    n = struct.unpack('B', f.read(1))[0]
    if n < 0xfd:
        return n
    if n == 0xfd:
        return struct.unpack('<H', f.read(2))[0]
    if n == 0xfe:
        return struct.unpack('<I', f.read(4))[0]
    return struct.unpack('<Q', f.read(8))[0]


def write_compact_size(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b'\xfd' + struct.pack('<H', n)
    if n <= 0xffffffff:
        return b'\xfe' + struct.pack('<I', n)
    return b'\xff' + struct.pack('<Q', n)


# ── Entry read / write ─────────────────────────────────────────────────────────

def read_entry_v2(f):
    """
    Read one AddrInfo in V2_DISK / BIP155 format (format >= 3).

    Layout:
      uint32  stored_format_version
      uint32  nTime
      CompactSize nServices
      uint8   net_id          }
      CompactSize addr_len    }  CNetAddr BIP155
      addr_len bytes addr     }
      uint16  port (BE)
      uint8   src_net_id      }
      CompactSize src_len     }  source CNetAddr BIP155
      src_len bytes src_addr  }
      int64   m_last_success
      int32   nAttempts
    """
    e = {}
    e['stored_fmt']   = struct.unpack('<I', f.read(4))[0]
    e['ntime']        = struct.unpack('<I', f.read(4))[0]
    e['nservices']    = read_compact_size(f)
    e['net_id']       = struct.unpack('B',  f.read(1))[0]
    alen              = read_compact_size(f)
    e['addr']         = f.read(alen)
    e['port']         = struct.unpack('>H', f.read(2))[0]
    e['src_net_id']   = struct.unpack('B',  f.read(1))[0]
    slen              = read_compact_size(f)
    e['src_addr']     = f.read(slen)
    e['last_success'] = struct.unpack('<q', f.read(8))[0]
    e['nattempts']    = struct.unpack('<i', f.read(4))[0]
    return e


def write_entry_v2(e):
    return (
        struct.pack('<I', e['stored_fmt'])
        + struct.pack('<I', e['ntime'])
        + write_compact_size(e['nservices'])
        + bytes([e['net_id']])
        + write_compact_size(len(e['addr'])) + e['addr']
        + struct.pack('>H', e['port'])
        + bytes([e['src_net_id']])
        + write_compact_size(len(e['src_addr'])) + e['src_addr']
        + struct.pack('<q', e['last_success'])
        + struct.pack('<i', e['nattempts'])
    )


def read_entry_v1(f):
    """
    Read one AddrInfo in V1_DISK format (format < 3).

    Layout:
      uint32  stored_format_version
      uint32  nTime
      uint64  nServices
      16 bytes addr (IPv4-in-IPv6 mapping or raw IPv6)
      uint16  port (BE)
      16 bytes source addr (CNetAddr V1)
      int64   m_last_success
      int32   nAttempts
    """
    e = {}
    e['stored_fmt']   = struct.unpack('<I', f.read(4))[0]
    e['ntime']        = struct.unpack('<I', f.read(4))[0]
    e['nservices']    = struct.unpack('<Q', f.read(8))[0]
    e['addr']         = f.read(16)
    e['port']         = struct.unpack('>H', f.read(2))[0]
    e['src_addr']     = f.read(16)
    e['last_success'] = struct.unpack('<q', f.read(8))[0]
    e['nattempts']    = struct.unpack('<i', f.read(4))[0]
    return e


def write_entry_v1(e):
    return (
        struct.pack('<I', e['stored_fmt'])
        + struct.pack('<I', e['ntime'])
        + struct.pack('<Q', e['nservices'])
        + e['addr']
        + struct.pack('>H', e['port'])
        + e['src_addr']
        + struct.pack('<q', e['last_success'])
        + struct.pack('<i', e['nattempts'])
    )


# ── Bucket-table reader ────────────────────────────────────────────────────────

def read_bucket_table_raw(f):
    """
    Read the full 1024-bucket new-table index and return the raw bytes.
    The bucket table structure does not depend on nTime, so we copy it unchanged.
    """
    out = b''
    for _ in range(ADDRMAN_NEW_BUCKET_COUNT):
        raw = f.read(4)
        out += raw
        num = struct.unpack('<i', raw)[0]
        if num > 0:
            chunk = f.read(num * 4)
            out += chunk
    return out


# ── Main patch function ────────────────────────────────────────────────────────

def patch_peers_dat(path, days_old=31):
    with open(path, 'rb') as fh:
        raw = fh.read()

    total  = len(raw)
    body   = raw[:-32]   # everything except the trailing 32-byte checksum
    stored_cksum = raw[-32:]

    # Verify checksum before touching anything
    computed = hashlib.sha256(hashlib.sha256(body).digest()).digest()
    if computed != stored_cksum:
        sys.exit(f"ERROR: checksum mismatch on '{path}' — file may be corrupt.")

    f = io.BytesIO(raw)

    # ── Header ────────────────────────────────────────────────────────────────
    magic  = f.read(4)
    fmt    = struct.unpack('B', f.read(1))[0]
    compat = struct.unpack('B', f.read(1))[0]
    nkey   = f.read(32)
    n_new    = struct.unpack('<i', f.read(4))[0]
    n_tried  = struct.unpack('<i', f.read(4))[0]
    n_ubuckets_raw = f.read(4)   # stored as nUBuckets ^ (1<<30); copied unchanged

    use_v2 = (fmt >= FORMAT_V3_BIP155)
    read_entry  = read_entry_v2  if use_v2 else read_entry_v1
    write_entry = write_entry_v2 if use_v2 else write_entry_v1

    print(f"peers.dat: format={fmt}  nNew={n_new}  nTried={n_tried}  "
          f"encoding={'V2/BIP155' if use_v2 else 'V1'}")

    # ── Read and patch entries ─────────────────────────────────────────────────
    stale_time = int(time.time()) - days_old * 24 * 3600
    new_entries = []
    old_entries = []

    for i in range(n_new + n_tried):
        e = read_entry(f)
        old_entries.append(e['ntime'])
        e['ntime'] = stale_time
        new_entries.append(e)

    # ── Bucket table (unchanged) ───────────────────────────────────────────────
    bucket_raw = read_bucket_table_raw(f)

    # ── Asmap version: 32-byte uint256, present when format >= V2_ASMAP ───────
    asmap_raw = b''
    if fmt >= FORMAT_V2_ASMAP:
        asmap_raw = f.read(32)

    # Sanity: we should have consumed exactly (total - 32) bytes
    if f.tell() != total - 32:
        print(f"  Warning: expected to read {total-32} bytes, "
              f"got {f.tell()} — output may be wrong.")

    # ── Reassemble ────────────────────────────────────────────────────────────
    new_body = magic
    new_body += bytes([fmt])
    new_body += bytes([compat])
    new_body += nkey
    new_body += struct.pack('<i', n_new)
    new_body += struct.pack('<i', n_tried)
    new_body += n_ubuckets_raw

    for e in new_entries:
        new_body += write_entry(e)

    new_body += bucket_raw
    new_body += asmap_raw

    new_cksum = hashlib.sha256(hashlib.sha256(new_body).digest()).digest()
    new_body  += new_cksum

    # ── Write back ────────────────────────────────────────────────────────────
    with open(path, 'wb') as fh:
        fh.write(new_body)

    total_addrs = n_new + n_tried
    print(f"Patched {total_addrs} address(es) — nTime set to "
          f"{stale_time} ({days_old} days ago).")
    if old_entries:
        now = int(time.time())
        ages = [(now - t) / 86400 for t in old_entries]
        print(f"  Old nTime range: {min(ages):.1f}d – {max(ages):.1f}d ago")
    print(f"  New nTime: {stale_time}  ({days_old}.0 days ago)")
    print(f"  File size: {len(new_body)} bytes  (checksum OK)")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 patch_peers_dat.py <peers.dat> [days_old]")

    path     = sys.argv[1]
    days_old = int(sys.argv[2]) if len(sys.argv) > 2 else 31

    patch_peers_dat(path, days_old)
