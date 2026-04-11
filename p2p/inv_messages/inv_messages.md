INV message 

A peer sends an inv message when it wants announce an object it has or it has received.



# Transaction Relay Decision  Version Handshake in ProcessMessage 

The decision of which peers we relay transactions to starts at the 
version handshake.

When we receive an incoming connection, we process the peer's version 
message in `ProcessMessage()`.

While processing it, we check:
- Is this a block-only connection?
- Is this a feeler connection?

If either is true, we do not set up tx relay for this peer.

If neither is true, AND the peer sent `fRelay=true` (or we are offering 
NODE_BLOOM), we call:

    auto* const tx_relay = peer.SetTxRelay();

`SetTxRelay()` is a setter function defined on the `Peer` struct. It 
allocates a `TxRelay` struct via a `unique_ptr` and returns a raw 
pointer to it. This struct holds all the per-peer state needed for 
transaction relay:
- `m_tx_inventory_to_send` - txs queued to announce
- `m_tx_inventory_known_filter` - what the peer already knows
- `m_next_inv_send_time` - the trickle timer
- `m_fee_filter_received` - the peer's feerate floor
- `m_bloom_filter` - the peer's SPV bloom filter if set
- `m_relay_txs` - whether this peer wants tx announcements

Note: `fRelay` defaults to `true`. It is only `false` if the peer 
explicitly sent `fRelay=false` in their version message (BIP37 opt-out).

After calling `SetTxRelay()`, we set:

    tx_relay->m_relay_txs = fRelay;

And if `fRelay` is true, we also set on `CNode`:

    pfrom.m_relays_txs = true;

`m_relays_txs` is an `atomic_bool` on `CNode` that indicates whether 
this peer will receive transaction relay from us.


for Peers with Bloom filters 

they send us this message 

`msg_type == NetMsgType::FILTERLOAD`
when we receive this message the peer is saying 
only send me blocks and transactions that match my filter 
and then we start checking different conditions
1. do WE even offer NODE_BLOOM?
`(!(peer.m_our_services & NODE_BLOOM))`
2. Create an empty CBloomFilter object and fill it with data
`
CBloomFilter filter;
vRecv >> filter;
`
3. Filter should never be too big
`if (!filter.IsWithinSizeConstraints()`

4. Store it and turn on tx relay
`peer.GetTxRelay()` we first check that this getter does not return an empty pointer 
meaning the pointer was set by SetTxRelay() and that we are ready to relay 

5. set relay fields to be True 
`m_relay_txs = true ` -- this is a bool in struct TxRelay which is true if we are going to relay a transaction to a peer
`pfrom.m_bloom_filter_loaded = true;` -- this is a CNode bool and we use to check if this peer has loaded a bloom filter
`pfrom.m_relays_txs = true;` -- this is a bool in CNode wether we should relay transaction to this peer is one way true -> false


6. `FILTERCLEAR ` when a peer want to clear the previous bloom filter and for us to set full transaction relay


we check again are we offering Node_BLoom

and then check the TXRelay Pointer 

`auto tx_relay = peer.GetTxRelay();`  

returns either a TxRelay* or nullptr

tx_relay->m_bloom_filter = nullptr; we set the bloom filter to be null indicating that we are clearing the bloom filter
tx_relay->m_relay_txs = true; this is the its the field in TxRelay Struct becomes true so we can still relay this to the peer

pfrom.m_bloom_filter_loaded = false; --bloom filter is no longer for this peer 
pfrom.m_relays_txs = true; -- cnode fields for relaying trannsactions also becomes true 




note there are three mesages that decided if we relay a transaction or not 


`pfrom.m_relays_txs` is a one-way flag on CNode — once true, 
it never goes back to false. It is distinct from 
`TxRelay::m_relay_txs` which CAN be toggled.



# How transactions arrive and get relayed

Transactions come from either:
- another peer sending us a `tx` message
- our own wallet via BroadcastTransaction()

## From a peer — msg_type == NetMsgType::TX

1. Are we a blocks-only node? → disconnect, return
2. Are we in IBD? → ignore, return
3. Deserialize the tx from the message:
       CTransactionRef ptx;
       vRecv >> TX_WITH_WITNESS(ptx);
4. Mark the sender as knowing this tx (AddKnownTx)
   so we don't announce it back to them
5. Ask txdownloadman: should we validate?
   ReceivedTx() returns should_validate = true/false

   if should_validate = false:
       we already have this tx
       but if peer has ForceRelay permission
       AND tx is in mempool → InitiateTxBroadcastToAll()
       (relay again even without revalidating — trusted peer)

   if should_validate = true:
       validate: m_chainman.ProcessTransaction(ptx)
           VALID   → ProcessValidTx()
                       └→ InitiateTxBroadcastToAll()
                            └→ queue in m_tx_inventory_to_send per peer
           INVALID → ProcessInvalidTx()
                       └→ maybe store as orphan
                auto tx_relay = peer.GetTxRelay()


send Messages 



## BIP35 Mempool Response

```cpp
if (fSendTrickle && tx_relay->m_send_mempool) {
```

Two conditions must be true:
- timer has fired (fSendTrickle = true)
- peer requested our mempool (m_send_mempool = true)

```cpp
tx_relay->m_send_mempool = false;
```
Reset immediately — only respond to mempool request once.

```cpp
const CFeeRate filterrate{tx_relay->m_fee_filter_received.load()};
```
Load this peer's minimum feerate — transactions below this rate
will not be sent to them.

Then we loop through ALL transactions in our mempool:

```cpp
for (const auto& txinfo : vtxinfo) {
```

For each tx:

1. get txid and wtxid from the tx
2. build the correct inv type for this peer:
   - wtxid relay peer → MSG_WTX with wtxid
   - legacy peer      → MSG_TX  with txid

3. remove from m_tx_inventory_to_send:
```cpp
tx_relay->m_tx_inventory_to_send.erase(wtxid);
```
Since we are about to announce this tx via the mempool dump,
we don't need it in the regular send queue anymore.

4. feerate check:
```cpp
if (txinfo.fee < filterrate.GetFee(txinfo.vsize)) continue;
```
Skip txs below the peer's minimum feerate — they won't
accept them into their mempool anyway.

5. bloom filter check:
```cpp
if (tx_relay->m_bloom_filter) {
    if (!tx_relay->m_bloom_filter->IsRelevantAndUpdate(*txinfo.tx)) continue;
}
```
Only relevant for SPV peers. If peer has no bloom filter
this check is skipped entirely and all txs pass through.
If peer has a bloom filter, only send txs that match it.

6. mark as known and add to inv:
```cpp
tx_relay->m_tx_inventory_known_filter.insert(inv.hash);
vInv.push_back(inv);
```
Mark this tx as known to this peer so we don't announce
it again later. Then add to the inv vector.

7. flush if inv vector is full:
```cpp
if (vInv.size() == MAX_INV_SZ) {
    MakeAndPushMessage(node, NetMsgType::INV, vInv);
    vInv.clear();
}
```
Send immediately if we hit the max inv size, then
start a fresh vector for remaining txs.


Scheduled sending  time must always bee in the past 
m_next_inv_send_time < current_time

m_next_inv_send_time = 10:00:05  (scheduled time)
current_time         = 10:00:06  (now)

10:00:05 < 10:00:06 = true
    └→ scheduled time is in the past
    └→ we are overdue
    └→ fSendTrickle = true
    └→ send now


m_next_inv_send_time = 10:00:05  (scheduled time)
current_time         = 10:00:03  (now)

10:00:05 < 10:00:03 = false
    └→ scheduled time is in the FUTURE
    └→ too early
    └→ fSendTrickle = false
    └→ wait

NoBan peer (whitelisted/local)
    └→ fSendTrickle = true IMMEDIATELY
    └→ timer check is irrelevant
    └→ always sends, no waiting

normal peer (no NoBan permission)
    └→ fSendTrickle starts as false
    └→ MUST wait for timer
    └→ inbound  → wait ~5s
    └→ outbound → wait ~2s

NoBan     ->  no timer needed  ->  send whenever SendMessages() runs
no NoBan  ->  timer required   ->  send only when scheduled time has passed




# SendMessages() — Transaction Inventory Drain Loop

## Overview

This is the normal tx relay path. When the trickle timer fires for a peer
(`fSendTrickle = true`), we drain `m_tx_inventory_to_send` and build an
`inv` message to announce transactions to this peer.

---

## Step 1 — Collect all candidates from the queue

```cpp
std::vector<std::set<Wtxid>::iterator> vInvTx;
vInvTx.reserve(tx_relay->m_tx_inventory_to_send.size());
for (std::set<Wtxid>::iterator it = tx_relay->m_tx_inventory_to_send.begin(); 
     it != tx_relay->m_tx_inventory_to_send.end(); it++) {
    vInvTx.push_back(it);
}
```

`m_tx_inventory_to_send` is the queue of wtxids we need to announce to
this peer. It was populated by `InitiateTxBroadcastToAll()` when txs
were accepted to the mempool.

We do NOT copy the wtxids themselves — we copy **iterators** (pointers
into the set) so we can erase from the set efficiently later in O(1).

We call `reserve()` first to pre-allocate memory for the vector,
avoiding multiple re-allocations as we fill it.

```
m_tx_inventory_to_send (set):
    [ wtxid1, wtxid2, wtxid3, wtxid4, wtxid5 ]

vInvTx (vector after loop):
    [ &wtxid1, &wtxid2, &wtxid3, &wtxid4, &wtxid5 ]
```

---

## Step 2 — Load this peer's feerate filter

```cpp
const CFeeRate filterrate{tx_relay->m_fee_filter_received.load()};
```

`m_fee_filter_received` is an `atomic<CAmount>` stored on `TxRelay`.
It is set when the peer sends us a `feefilter` message — it represents
the peer's minimum feerate threshold.

We wrap it in a `CFeeRate` object so we can call `GetFee(vsize)` later
to calculate the minimum fee for a tx of a given size.

This is a **per peer** value — one threshold that applies to ALL txs
we consider announcing to this peer.

```
peer's feefilter = 2 sat/vbyte  (set once via feefilter message)
    └→ applies to every tx in the drain loop
```

---

## Step 3 — Heap sort by fee rate and topology

```cpp
CompareInvMempoolOrder compareInvMempoolOrder(&m_mempool);
std::make_heap(vInvTx.begin(), vInvTx.end(), compareInvMempoolOrder);
```

### Why a heap instead of a full sort?

```
queue has 1000 txs
broadcast_max = 75    ← we only send 75

full sort:
    └→ sort all 1000 txs   ← wasted work on 925 txs
    └→ O(n log n)

heap:
    └→ arrange into heap   ← O(n)
    └→ pop top 75          ← O(75 log n)
    └→ never touch other 925
    └→ much more efficient
```

### What is `CompareInvMempoolOrder`?

```cpp
class CompareInvMempoolOrder {
    const CTxMemPool* m_mempool;
public:
    explicit CompareInvMempoolOrder(CTxMemPool* mempool) : m_mempool{mempool} {}
    bool operator()(std::set<Wtxid>::iterator a, std::set<Wtxid>::iterator b) {
        return m_mempool->CompareMiningScoreWithTopology(*b, *a);
    }
};
```

A comparator class that takes our mempool pointer and uses it to rank
transactions by:

1. **Topology** — parent txs before child txs
2. **Fee rate** — higher feerate txs first

### Why topology beats fee rate

```
tx D (parent)  fee = 6 sat/vbyte
tx E (child)   fee = 9 sat/vbyte  ← higher fee but depends on D

correct order: D → E
    └→ peer cannot validate E without D
    └→ topology always wins over fee rate
```

### Example heap

```
queue: [ tx1(10), tx2(8), tx3(6 parent), tx5(9 child of tx3) ]

after make_heap:
        tx1 (10 sat/vbyte)       ← top
       /                \
   tx2 (8)            tx3 (6)    ← parent, before tx5
                      /
                  tx5 (9)        ← child, after tx3

pop order:
    pop 1 → tx1  (highest fee, no dependencies)
    pop 2 → tx2  (next highest fee)
    pop 3 → tx3  (parent, must come before tx5)
    pop 4 → tx5  (child, safe now, tx3 already announced)
```

---

## Step 4 — Calculate broadcast maximum

```cpp
unsigned int nRelayedTransactions = 0;
size_t broadcast_max{INVENTORY_BROADCAST_TARGET + 
                    (tx_relay->m_tx_inventory_to_send.size()/1000)*5};
broadcast_max = std::min<size_t>(INVENTORY_BROADCAST_MAX, broadcast_max);
```

### Constants

```
INVENTORY_BROADCAST_PER_SECOND       = 14
INBOUND_INVENTORY_BROADCAST_INTERVAL = 5s
INVENTORY_BROADCAST_TARGET           = 14 * 5 = 70 txs
INVENTORY_BROADCAST_MAX              = 1000 txs (hard cap)
```

Note: `INVENTORY_BROADCAST_TARGET` always uses the inbound interval (5s)
even for outbound peers. Outbound peers get higher throughput naturally
because their timer fires more frequently (~2s vs ~5s).

### The formula

```
broadcast_max = INVENTORY_BROADCAST_TARGET + (queue_size/1000) * 5

queue =    0 txs  →  70 + 0   = 70
queue =  100 txs  →  70 + 0   = 70  (integer division: 100/1000 = 0)
queue = 1000 txs  →  70 + 5   = 75
queue = 2000 txs  →  70 + 10  = 80
queue = 5000 txs  →  70 + 25  = 95
queue = 9000 txs  →  70 + 45  = 115
```

Hard cap always applied:
```
broadcast_max = min(1000, broadcast_max)
```

### Why not drain the entire queue?

```
we have many peers
each peer fires timer at different times
    └→ most txs reach the network quickly anyway
         └→ no need to flood one peer with
            hundreds of announcements at once
         └→ network capacity respected
         └→ other peers pick up the slack
```

### Outbound vs inbound

```
inbound  → timer fires every ~5s → 70 txs per fire = 14 txs/s
outbound → timer fires every ~2s → 70 txs per fire = 35 txs/s

same broadcast_max, faster timer = higher outbound throughput
```

---

## Step 5 — Drain loop with 4 filters

```cpp
while (!vInvTx.empty() && nRelayedTransactions < broadcast_max) {
```

Two exit conditions:
```
vInvTx.empty()                         ← no more candidates
nRelayedTransactions >= broadcast_max  ← sent enough this round
```

### Pop highest priority tx from heap

```cpp
std::pop_heap(vInvTx.begin(), vInvTx.end(), compareInvMempoolOrder);
std::set<Wtxid>::iterator it = vInvTx.back();
vInvTx.pop_back();
auto wtxid = *it;
```

`std::pop_heap` moves the highest priority item to the BACK of the
vector then re-arranges the rest into a valid heap:

```
before: [ tx1, tx2, tx3, tx5 ]  (tx1 is top of heap)

after pop_heap:
        [ tx2, tx5, tx3, tx1 ]   ← tx1 moved to back

after pop_back:
        [ tx2, tx5, tx3 ]        ← still a valid heap
```

### Always erase from queue first

```cpp
tx_relay->m_tx_inventory_to_send.erase(it);
```

Removed from queue **regardless** of whether it passes filters.
This keeps the queue clean and prevents dead txs from accumulating.

### Filter 1 — still in mempool?

```cpp
auto txinfo = m_mempool.info(wtxid);
if (!txinfo.tx) continue;
```

Between queue time and send time (~2-5s) the tx may have been:
```
included in a block    → removed from mempool
evicted (full mempool) → removed from mempool
replaced by RBF        → removed from mempool
```

If not in mempool → `txinfo.tx = nullptr` → skip.
`nRelayedTransactions` is NOT incremented.

### Build correct inv type for this peer

```cpp
const auto inv = peer.m_wtxid_relay ?
    CInv{MSG_WTX, wtxid.ToUint256()} :
    CInv{MSG_TX, txinfo.tx->GetHash().ToUint256()};
```

```
modern peer (wtxid relay)  → MSG_WTX + wtxid
legacy peer                → MSG_TX  + txid
                              (convert wtxid → txid via mempool lookup)
```

The queue always stores `wtxid` internally. Conversion to `txid`
happens here at send time for legacy peers only.

### Filter 2 — peer already knows this tx?

```cpp
if (tx_relay->m_tx_inventory_known_filter.contains(inv.hash)) continue;
```

`m_tx_inventory_known_filter` tracks txs known to this peer in BOTH
directions:
```
peer announced tx TO US  → AddKnownTx() → inserted into filter
WE announced tx TO peer  → inserted after successful announce
```

This is a second check — `InitiateTxBroadcastToAll()` already checked
this at queue time, but the peer may have learned about the tx in the
meantime (e.g. received it from another peer).

### Filter 3 — above peer's feerate floor?

```cpp
if (txinfo.fee < filterrate.GetFee(txinfo.vsize)) continue;
```

```
filterrate.GetFee(txinfo.vsize)
    └→ peer's feerate × tx size in vbytes
    └→ minimum fee peer will accept for this tx size

example:
    peer feefilter = 2 sat/vbyte
    tx vsize = 150 vbytes
    minimum fee = 2 * 150 = 300 sats

    tx fee = 400 sats → 400 < 300? NO  → announce ✓
    tx fee = 200 sats → 200 < 300? YES → skip    ✗
```

### Filter 4 — bloom filter match?

```cpp
if (tx_relay->m_bloom_filter && 
    !tx_relay->m_bloom_filter->IsRelevantAndUpdate(*txinfo.tx)) continue;
```

```
peer has no bloom filter  → skip this check entirely, all txs pass
peer has bloom filter     → does tx match filter?
                                NO  → skip
                                YES → proceed
```

Only relevant for SPV/lite peers that sent a `filterload` message.

### Passed all filters — add to inv

```cpp
vInv.push_back(inv);
nRelayedTransactions++;
```

`nRelayedTransactions` only increments when a tx PASSES all 4 filters.
Dropped txs do not count — we may pop more than `broadcast_max` items
from the heap to actually relay `broadcast_max` txs:

```
broadcast_max = 75
popped 100 txs from heap
    └→ 25 dropped (mempool, known filter, feerate, bloom)
    └→ 75 actually announced
    └→ loop exits when nRelayedTransactions = 75
```

### Flush if inv vector hits max size

```cpp
if (vInv.size() == MAX_INV_SZ) {
    MakeAndPushMessage(node, NetMsgType::INV, vInv);
    vInv.clear();
}
```

`MAX_INV_SZ = 50000`. With `broadcast_max = 75` this never triggers
in normal operation. It is a safety net mainly used in the BIP35
mempool dump path where the entire mempool is announced at once.

### Mark as known after announcing

```cpp
tx_relay->m_tx_inventory_known_filter.insert(inv.hash);
```

After announcing a tx we immediately mark it as known to this peer
so we never announce it again.

---

## Step 6 — Snapshot mempool sequence

```cpp
LOCK(m_mempool.cs);
tx_relay->m_last_inv_sequence = m_mempool.GetSequence();
```

Records the current mempool sequence number after our announcements.
The mempool sequence increments every time a tx is added or removed.

```
"peer knows everything in mempool up to sequence N"
    └→ used by info_for_relay() to serve GETDATA requests
         └→ we can respond to getdata for anything
            we just announced
```

---

## Step 7 — Final flush

```cpp
if (!vInv.empty())
    MakeAndPushMessage(node, NetMsgType::INV, vInv);
```

Any remaining txs in `vInv` that have not been sent yet get flushed
here. This handles the case where the loop exited before hitting
`MAX_INV_SZ`.

---

## Complete flow summary

```
m_tx_inventory_to_send (populated by InitiateTxBroadcastToAll)
        │
        ▼
collect all into vInvTx (iterators)
        │
        ▼
load peer feerate (filterrate)
        │
        ▼
heap sort by fee + topology (CompareInvMempoolOrder)
        │
        ▼
calculate broadcast_max (70 base + queue factor, cap 1000)
        │
        ▼
while queue not empty AND under broadcast_max:
    pop highest priority tx from heap
    erase from m_tx_inventory_to_send (always)
        │
        ├── Filter 1: not in mempool?     → drop (continue)
        ├── Filter 2: peer knows it?      → drop (continue)
        ├── Filter 3: below feefilter?    → drop (continue)
        ├── Filter 4: bloom filter miss?  → drop (continue)
        └── passed all filters?
                └→ vInv.push_back(inv)
                   nRelayedTransactions++
                   known_filter.insert(hash)
        │
        ▼
snapshot mempool sequence (m_last_inv_sequence)
        │
        ▼
MakeAndPushMessage(node, NetMsgType::INV, vInv)  ← sent to peer
```

what is a dead transaction 

T=0s   tx accepted to mempool
            └→ InitiateTxBroadcastToAll()
                 └→ m_tx_inventory_to_send.insert(wtxid)

        ← anything can happen to the mempool here →

T=5s   SendMessages() timer fires
            └→ drain loop
                 └→ m_mempool.info(wtxid) → nullptr
                      └→ dead tx detected


Mempool

static constexpr unsigned int DEFAULT_MAX_MEMPOOL_SIZE_MB{300};
this is the total size of all transactions in our mempool combined

300 MB = maximum total size of all transactions in the mempool
    └→ NOT a count of transactions
    └→ measured by total virtual bytes of all txs combined



static constexpr unsigned int INVENTORY_BROADCAST_MAX = 1000;
INVENTORY_BROADCAST_PER_SECOND = 14
meaning we are relaying 14 transactions per second 
so if our queue size if m_tx_inventory_to_send = 86000


size_t broadcast_max{INVENTORY_BROADCAST_TARGET + (tx_relay->m_tx_inventory_to_send.size()/1000)*5};
                    broadcast_max = std::min<size_t>(INVENTORY_BROADCAST_MAX, broadcast_max);
broadcast_max = std::min<size_t>(INVENTORY_BROADCAST_MAX, broadcast_max);
static constexpr auto INBOUND_INVENTORY_BROADCAST_INTERVAL{5s};
static constexpr unsigned int INVENTORY_BROADCAST_PER_SECOND{14};
/** Target number of tx inventory items to send per transmission. */
static constexpr unsigned int INVENTORY_BROADCAST_TARGET = INVENTORY_BROADCAST_PER_SECOND * count_seconds(INBOUND_INVENTORY_BROADCAST_INTERVAL);

so if our queue size if m_tx_inventory_to_send = 86000
INVENTORY_BROADCAST_PER_SECOND{14};
 INVENTORY_BROADCAST_TARGET = 14 * 5 = 70 
 size_t broadcast_max{70+ 86000.size()/1000 * 5 } = 500
broadcast_max = std::min<size_t>(INVENTORY_BROADCAST_MAX, broadcast_max);
std::min<size_t>(500, 1000)

soo 500


queue_size = 700,000
INVENTORY_BROADCAST_PER_SECOND = 14
INVENTORY_BROADCAST_TARGET = 14 * 5 = 70

size_t broadcast_max{70 + (700000/1000) * 5}
                   = 70 + 700 * 5
                   = 70 + 3500
                   = 3570

broadcast_max = std::min<size_t>(INVENTORY_BROADCAST_MAX, broadcast_max);
std::min<size_t>(3570, 1000)

so 1000   ← hard cap kicks in!



maxmempool = 300MB (default)
    └→ limits total size of mempool
         └→ limits how many txs can exist in mempool
              └→ limits how many txs get added to queue
                   └→ limits queue_size
                        └→ limits broadcast_max






