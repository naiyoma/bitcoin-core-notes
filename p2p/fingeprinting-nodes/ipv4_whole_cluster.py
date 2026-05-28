"""
cluster_all_ipv4.py — find dense clusters of nodes that share peers heavily,
across the entire IPv4 table.

Methodology:
  1. Filter peer_addrs to only those known by 2-100 nodes.
     (Universally-known peers like DNS seeds add noise, not signal.)
  2. Compute pairwise overlap on these "discriminating" peers only.
  3. Build a weighted graph and run Louvain community detection.
"""
import asyncio
import asyncpg
import networkx as nx
import networkx.algorithms.community as nx_comm
from collections import Counter

DB_CONFIG = dict(user='btc_crawler_user', password='1234',
                 database='btc_crawler', host='localhost', port=5432)

# Only keep peers known by between this many nodes.
# Below: noise (singleton peers).  Above: universal peers (everyone knows them).
PEER_POPULARITY_MIN = 2
PEER_POPULARITY_MAX = 100

# A pair of nodes is connected if they share this many "discriminating" peers.
# Lower than before because we've already filtered out the noisy universal peers.
MIN_SHARED_PEERS = 100

# Hide tiny clusters
MIN_CLUSTER_SIZE = 3


async def main():
    conn = await asyncpg.connect(**DB_CONFIG, command_timeout=1800)

    print(f"Computing pairwise overlap on peers known by "
          f"{PEER_POPULARITY_MIN}-{PEER_POPULARITY_MAX} nodes...")
    print(f"Edge threshold: ≥{MIN_SHARED_PEERS} discriminating peers shared.")
    print("This may take a few minutes.\n")

    rows = await conn.fetch(f"""
        WITH selective_peers AS (
          SELECT peer_addr
          FROM april25th_ipv4_responses
          GROUP BY peer_addr
          HAVING COUNT(*) BETWEEN {PEER_POPULARITY_MIN} AND {PEER_POPULARITY_MAX}
        )
        SELECT
          a.node_addr AS node_a,
          b.node_addr AS node_b,
          COUNT(*)    AS shared_peers
        FROM april25th_ipv4_responses a
        JOIN april25th_ipv4_responses b
          ON a.peer_addr = b.peer_addr
         AND a.node_addr < b.node_addr
        WHERE a.peer_addr IN (SELECT peer_addr FROM selective_peers)
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

    # Edge weight distribution — useful for tuning
    weights = [d['weight'] for _, _, d in G.edges(data=True)]
    print(f"Edge weights: min={min(weights)}, max={max(weights)}, "
          f"avg={sum(weights)/len(weights):.0f}\n")

    # Louvain community detection
    print("Running community detection...")
    communities = nx_comm.louvain_communities(
        G, weight='weight', seed=42, resolution=1.0
    )
    big = sorted([c for c in communities if len(c) >= MIN_CLUSTER_SIZE],
                 key=len, reverse=True)

    print(f"\nFound {len(big)} clusters with ≥{MIN_CLUSTER_SIZE} nodes:\n")

    for i, comp in enumerate(big, 1):
        sub = G.subgraph(comp)
        if sub.number_of_edges() == 0:
            continue
        avg_w = sum(d['weight'] for _, _, d in sub.edges(data=True)) / sub.number_of_edges()
        density = nx.density(sub)
        slash16s = Counter(addr.split(':')[0].rsplit('.', 2)[0] for addr in comp)

        print(f"--- Cluster {i} ---")
        print(f"  Size:           {len(comp)} nodes")
        print(f"  Edges:          {sub.number_of_edges()}")
        print(f"  Avg shared:     {avg_w:.0f} discriminating peers")
        print(f"  Density:        {density:.2f}")
        print(f"  Top /16s:       {slash16s.most_common(5)}")
        print(f"  Sample members: {sorted(comp)[:6]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())