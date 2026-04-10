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
