"""
sybil_detection.py — find ipv6 nodes that return identical addr responses,
which is the wire-level signature of one physical Bitcoin Core instance
operating under multiple IP addresses.

Method:
  1. For each node, build a fingerprint = hash of its sorted (peer_addr, timestamp) list
  2. Group nodes by fingerprint
  3. Filter to groups where members live on different IP addresses
     (excludes same-IP-different-port cases, which are trivially the same instance)

Two strictness levels are reported:
  - STRICT: identical peer sets AND identical timestamps (highest-confidence Sybil)
  - LOOSE:  identical peer sets, timestamps may have drifted (cloned-snapshot Sybil)
"""
import asyncio
import asyncpg
from collections import Counter

DB_CONFIG = dict(user='btc_crawler_user', password='1234',
                 database='btc_crawler', host='localhost', port=5432)

# Ignore tiny responses — a node that returned only 1 peer giving false positives
MIN_RESPONSE_SIZE = 100


async def find_sybils(conn, table_name: str, strict: bool):
    """
    Find groups of cross-IP nodes returning identical responses.
    strict=True  → match (peer_addr, peer_timestamp) tuples
    strict=False → match peer_addr only
    """
    if strict:
        hash_expr = "string_agg(peer_addr || ':' || peer_timestamp, ',' ORDER BY peer_addr)"
    else:
        hash_expr = "string_agg(peer_addr, ',' ORDER BY peer_addr)"

    return await conn.fetch(f"""
        WITH fp AS (
          SELECT
            node_addr,
            SPLIT_PART(node_addr, ':', 1) AS ip,
            md5({hash_expr}) AS h,
            COUNT(*) AS peer_count
          FROM {table_name}
          GROUP BY node_addr
          HAVING COUNT(*) >= {MIN_RESPONSE_SIZE}
        )
        SELECT
          peer_count,
          h AS fingerprint,
          COUNT(*) AS group_size,
          COUNT(DISTINCT ip) AS distinct_ips,
          array_agg(node_addr ORDER BY node_addr) AS members
        FROM fp
        GROUP BY peer_count, h
        HAVING COUNT(*) > 1
           AND COUNT(DISTINCT ip) > 1
        ORDER BY group_size DESC, peer_count DESC
    """)


def report(label, groups):
    print(f"\n{'=' * 70}")
    print(f"{label}")
    print(f"{'=' * 70}")

    if not groups:
        print("No cross-IP groups found.")
        return

    total_pairs = sum(g['group_size'] for g in groups)
    total_groups = len(groups)
    print(f"Found {total_groups} cross-IP groups containing {total_pairs} nodes total.\n")

    # Group-size distribution
    size_dist = Counter(g['group_size'] for g in groups)
    print("Group size distribution:")
    for size in sorted(size_dist.keys()):
        print(f"  {size_dist[size]} group(s) of size {size}")

    # Print each group
    print(f"\n{'Group':<6} {'Size':<6} {'Peers':<8} Members")
    print("-" * 70)
    for i, g in enumerate(groups, 1):
        members_str = ", ".join(g['members'])
        if len(members_str) > 60:
            members_str = members_str[:57] + "..."
        print(f"{i:<6} {g['group_size']:<6} {g['peer_count']:<8} {members_str}")

    # Optional: print full members for groups of size > 2
    bigger = [g for g in groups if g['group_size'] > 2]
    if bigger:
        print(f"\nLarger-than-pair groups ({len(bigger)}):")
        for g in bigger:
            print(f"  {g['group_size']} nodes, {g['peer_count']} peers each:")
            for m in g['members']:
                print(f"    {m}")


async def main():
    conn = await asyncpg.connect(**DB_CONFIG, command_timeout=600)

    print(f"Sybil detection on april25th_ipv6_responses")
    print(f"(only nodes returning ≥{MIN_RESPONSE_SIZE} peers are considered)")

    print("\nRunning STRICT match (peer_addr + peer_timestamp identical)...")
    strict = await find_sybils(conn, 'april25th_ipv6_responses', strict=True)
    report("STRICT match — wire-level Sybils (one process, multiple IPs)", strict)

    print("\nRunning LOOSE match (peer_addr identical, timestamps may differ)...")
    loose = await find_sybils(conn, 'april25th_ipv6_responses', strict=False)
    report("LOOSE match — cloned-snapshot Sybils (same peers.dat ancestry)", loose)

    # The interesting delta: nodes that match on peer set but not timestamp
    strict_hashes = {g['fingerprint'] for g in strict}
    loose_only = [g for g in loose if g['fingerprint'] not in strict_hashes]
    report("LOOSE-only — Sybils with timestamp drift (older clones)", loose_only)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())