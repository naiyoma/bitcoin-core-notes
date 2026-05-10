# Reproducing Bitcoin Core's m_tx_inventory_to_send Queue Bloat


my goal: flood mempool and observer cpu usage 

## The mechanism (what causes the bug)

### Per-peer queue structure

For every connected peer, Bitcoin Core maintains a struct called `TxRelay` containing:

- `m_tx_inventory_to_send` a `std::set<Wtxid>` of transactions to announce to this peer
- `m_tx_inventory_known_filter` a `CRollingBloomFilter` of transactions this peer already knows about
- `m_relay_txs`, `m_fee_filter_received`, `m_bloom_filter` other per-peer state

These structures are **per-peer**. If a node has 100 peers, it has 100 separate queues.

### How queues fill

When a transaction enters the node's mempool, `InitiateTxBroadcastToAll()` runs. For each peer, it checks whether the peer's `m_tx_inventory_known_filter` contains this tx. If not, the wtxid is added to that peer's `m_tx_inventory_to_send`.

The known-filter is populated two ways:
1. **Inbound:** the peer announces a tx to us, we add it to their known-filter
2. **Outbound:** we successfully announce a tx to the peer, we add it to their known-filter

A "honest" peer triggers path 1 frequently. Their known-filter grows fast, so most txs are skipped from queueing. Their queue stays small.

A "silent" peer never triggers path 1. Their known-filter stays nearly empty. Every new tx gets queued for them. Their queue grows unbounded.

### How queues drain

`SendMessages()` runs on `b-msghand` for each peer at trickle intervals (~5s for inbound peers, ~2s for outbound). Inside, for each peer:

1. Copy iterators from `m_tx_inventory_to_send` into a vector — O(N) where N = queue size
2. Run `std::make_heap` on that vector with a comparator that ranks by mining score and topology — O(N) in element count, but each comparison hits the mempool and walks ancestor sets, so the constant factor is heavy
3. Pop top entries until either the heap is exhausted or `broadcast_max` (~70-1000 entries) have been successfully sent
4. Each popped entry is checked against four filters (mempool presence, known-filter, feefilter, bloom filter)

The cost dominator is **step 2**  `make_heap` cost. It scales with N (queue size) and with the per-comparison cost (mempool ancestor walks).

### Why this saturates the thread

`b-msghand` is single-threaded. It handles message processing for *all* peers sequentially. With:
- 30 silent listeners
- ~10,000 entries per queue
- ~5-second trickle interval

Each cycle does 30 × `make_heap(10000)` operations. If each operation takes ~30ms, that's 900ms of work every 5 seconds = 18% sustained. With more peers or larger queues, this scales linearly until the thread is at 100%.

When `b-msghand` is saturated, all P2P message processing slows down. Pings get delayed. Blocks propagate slowly. Peers may time out and disconnect.

## My setup

### Topology

Four bitcoind tanks running in a Warnet/Minikube cluster:

- **tank-0000** — producer. Generates the transaction surge.
- **tank-0001** — observer. The node we measure. Has silent listeners attached.
- **tank-0002, tank-0003** — honest peers. Control group; their queues stay small because they reciprocate.

Plus: 30 silent listener peers (Python `P2PInterface` instances) attached to tank-0001. They accept inv messages but never send getdata, never send invs of their own, never reciprocate.

### Why this topology

I need **at least one silent peer** for the queue to grow. I need **honest peers as a control** to show the spike is specifically about silent peers, not just high tx volume. I need **a producer separate from the observer** so my measurement isn't polluted by tx-construction work on the observer itself.

## The three scenarios

### `miner_std.py`

Background utility. Mines one block every 600s on tank-0000.

Purpose: keep the chain alive. Without occasional blocks, mempools could expire entries (default mempool expiry is 14 days, so this is mostly a long-experiment concern). Also keeps the producer's wallet replenished if needed.

Run: `warnet run scenarios/miner_std.py

### `listener.py`

The threat model. Attaches N silent peers to the observer.

Each `SilentListener` is a `P2PInterface` subclass that:
- Completes the version/verack handshake (so it shows up as a real peer)
- Overrides `on_inv` to count incoming invs but **not** send getdata back
- Overrides `on_getdata` and `on_getheaders` to do nothing (suppresses default reflexes)
- Never initiates announcements

The key behavior: **bytesrecv_per_msg.getdata stays at zero**. That asymmetry is what causes the observer's known-filter for this peer to stay empty, which is what causes queue bloat.

Run: `warnet run scenarios/listener.py

After running, the observer's `getpeerinfo` shows 30 additional inbound peers from the listener pod's IP, all with growing `bytessent_per_msg.inv` and zero `bytesrecv_per_msg.getdata`.

### `tx_flood.py`

The trigger. Generates a controlled tx surge.

Strategy:
1. **Mine N+100 blocks to MiniWallet's address** so MiniWallet has N mature coinbases
2. **Build splitter wave**: for each coinbase, build a multi-output tx that fans the 50 BTC into 25 small outputs. 400 splitters × 25 outputs = 10,000 independent UTXOs
3. **Send splitters first**: their outputs become the parent UTXOs for the leaves
4. **Build leaf wave**: for each splitter output, pre-sign one self-transfer. All leaves have ancestor depth = 2 (well under the 25-ancestor mempool limit)
5. **Surge**: dump all 10,000 leaves via `sendrawtransaction` from 8 parallel worker threads
6. **Hold**: sleep 60s after surge so queues stay bloated for observation

The critical design choice: pre-signing in memory + parallel raw submission gets us 600-800 tx/s. Direct `sendmany` calls via the wallet would top out at ~10 tx/s due to wallet locks.

Run: `warnet run scenarios/tx_flood.py

## The measurement infrastructure

### Why three measurement tools


1. **kubectl `b-msghand` CPU monitor** — per-thread CPU usage on tank-0001
2. **Grafana CPU panel** — per-tank container CPU usage  
3. **Existing Grafana mempool panel** — per-tank mempool size

Together they tell the full story:
- The mempool panel proves txs are propagating (input)
- The CPU panel proves CPU is being consumed (output)
- The kubectl monitor proves the consumption is specifically in `b-msghand` (mechanism)

### kubectl monitor — the smoking gun

Reads `/proc/<bitcoind_pid>/task/<b_msghand_tid>/stat` once per second. Fields 14 and 15 are utime+stime in clock ticks (100/sec). Delta in ticks per second = CPU% on a 0-100 scale.

```bash
PID=$(kubectl exec tank-0001 -c bitcoincore -- pidof bitcoind)
TID=$(kubectl exec tank-0001 -c bitcoincore -- sh -c "
for t in /proc/$PID/task/*/; do
    [ \"\$(cat \$t/comm 2>/dev/null)\" = 'b-msghand' ] && basename \$t && break
done
")
PREV=$(kubectl exec tank-0001 -c bitcoincore -- awk '{print $14+$15}' /proc/$PID/task/$TID/stat)
while true; do
    sleep 1
    NOW=$(kubectl exec tank-0001 -c bitcoincore -- awk '{print $14+$15}' /proc/$PID/task/$TID/stat)
    echo "$(date +%H:%M:%S) b-msghand=$((NOW-PREV))%"
    PREV=$NOW
done
```

This isolates **specifically the message-handler thread**, not the whole container. If saturation shows up here but not on other threads (b-net, b-scheduler), the bug is specifically in message handling — which is where `make_heap` runs.

### Grafana CPU panel

PromQL: `sum by (pod) (rate(container_cpu_usage_seconds_total{pod=~"tank.*"}[2m]))`

Shows total container CPU per tank as a rate (cores per second). Coarser than the kubectl monitor — picks up all threads in the container, not just `b-msghand`. But useful for:

- **Comparing tanks side by side**: tank-0001 spikes, tank-0002/0003 stay flat. The contrast is the evidence.
- **Real-time visualization** during the experiment
- **Long-running observation** without keeping a terminal open

A value of 1.0 = one full core. During saturation tank-0001 hits ~0.95-1.05.

### Grafana mempool panel

Already existed in the default Warnet dashboard. Shows mempool size per tank.

During the experiment:
- tank-0000 (producer) jumps to 10000+ during surge
- tank-0001/2/3 climb as txs propagate via P2P
- tank-0001's growth rate is ~50 tx/s during the post-surge hold
- After ~5-10 minutes, blocks confirm and mempool drains

The shape of tank-0001's curve during the post-surge hold is the input that drives the CPU spike. Bigger mempool → bigger queues for silent listeners → bigger `make_heap` cost.

## What proves the bug

Three pieces of evidence aligned in time:

### Evidence 1: tank-0001 b-msghand spikes to 90%+

In one of my runs, the kubectl monitor captured:


![CPU spike during surge](inv_messages.png)