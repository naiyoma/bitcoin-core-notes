"""
cluster_256club.py — find dense sub-clusters within the 256-cap operator fleet.
Each cluster is a group of nodes that all heavily share peers with one another.
"""
import asyncio
import asyncpg
import networkx as nx
import networkx.algorithms.community as nx_comm
from collections import Counter

DB_CONFIG = dict(user='btc_crawler_user', password='1234',
                 database='btc_crawler', host='localhost', port=5432)

# Stricter threshold — 33 is expected from random sampling of the shared 2006 pool.
# Anything ≥ 50 is well above background noise.
MIN_SHARED_PEERS = 50

# Hide tiny groups
MIN_CLUSTER_SIZE = 3


async def main():
    conn = await asyncpg.connect(**DB_CONFIG)

    print(f"Fetching pairwise overlap (≥{MIN_SHARED_PEERS} shared peers) for 256-club...")
    rows = await conn.fetch(f"""
        WITH cluster AS (
          SELECT node_addr FROM april25th_ipv4_responses
          GROUP BY node_addr HAVING COUNT(*) = 256
        )
        SELECT
          a.node_addr AS node_a,
          b.node_addr AS node_b,
          COUNT(*)    AS shared_peers
        FROM april25th_ipv4_responses a
        JOIN april25th_ipv4_responses b
          ON a.peer_addr = b.peer_addr
         AND a.node_addr < b.node_addr
        WHERE a.node_addr IN (SELECT node_addr FROM cluster)
          AND b.node_addr IN (SELECT node_addr FROM cluster)
        GROUP BY a.node_addr, b.node_addr
        HAVING COUNT(*) >= {MIN_SHARED_PEERS}
    """)
    await conn.close()

    print(f"Got {len(rows)} edges above threshold.")
    if not rows:
        print("No edges above threshold — try lowering MIN_SHARED_PEERS.")
        return

    # Build weighted graph
    G = nx.Graph()
    for r in rows:
        G.add_edge(r['node_a'], r['node_b'], weight=r['shared_peers'])
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Louvain community detection — finds internally dense subgroups
    communities = nx_comm.louvain_communities(G, weight='weight',
                                              seed=42, resolution=1.5)
    big = sorted([c for c in communities if len(c) >= MIN_CLUSTER_SIZE],
                 key=len, reverse=True)

    print(f"\nFound {len(big)} clusters with ≥{MIN_CLUSTER_SIZE} nodes:\n")

    for i, comp in enumerate(big, 1):
        sub = G.subgraph(comp)
        avg_w = sum(d['weight'] for _, _, d in sub.edges(data=True)) / sub.number_of_edges() if sub.number_of_edges() else 0
        density = nx.density(sub)
        slash16s = Counter(addr.split(':')[0].rsplit('.', 2)[0] for addr in comp)

        print(f"--- Cluster {i} ---")
        print(f"  Size:           {len(comp)} nodes")
        print(f"  Edges:          {sub.number_of_edges()}")
        print(f"  Avg shared:     {avg_w:.1f} peers")
        print(f"  Density:        {density:.2f}  (1.0 = every pair connected)")
        print(f"  Top /16 subnets: {slash16s.most_common(3)}")
        print(f"  Sample members: {sorted(comp)[:8]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())