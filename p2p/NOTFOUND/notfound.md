Core message types and their roles
INV — Announcement: "I have these things." Unsolicited; sent whenever a peer has new transactions, blocks, or other data to advertise.
GETDATA — Request: "Send me these things." Sent in response to seeing an INV (or after accepting headers, etc.) to ask for the actual data.
NOTFOUND — Apology: "I don't have these things you asked for." Sent only as a response to GETDATA when the requested items aren't available.
TX / BLOCK — Delivery: the actual data being sent in response to GETDATA.
All three of INV, GETDATA, and NOTFOUND carry the same payload structure: a vector of CInv entries, where each entry is {type, hash} identifying an object. They share the data structure but have different semantic intents.
The standard flow
Peer ──── INV (1000 hashes) ────────────> Us       "I have these"
Peer <─── GETDATA (subset of those) ───── Us       "Send me these"
              ↓
Peer ──── TX (actual transactions) ─────> Us       success path
   OR
Peer ──── NOTFOUND (couldn't find them) > Us       failure path
Why NOTFOUND happens
NOTFOUND occurs in the gap between INV and GETDATA. Between when a peer announces a tx and when our GETDATA arrives back at them, the tx might have left their mempool because:

A new block confirmed it
RBF replaced it
Mempool eviction kicked it out
Expiry removed it after sitting too long

Block NOTFOUNDs are silently dropped by our handler — we only act on tx-related NOTFOUNDs because block download has its own timeout/retry mechanisms.
What our node does with received NOTFOUND
The handler dispatches to m_txdownloadman.ReceivedNotFound(), which:

Removes the in-flight request for (peer, tx_hash)
Tries another peer that announced the same tx, if any
Otherwise drops the announcement

For tx download, we DO track which GETDATAs we sent (via the TxRequestTracker state machine: CANDIDATE → REQUESTED → completed/failed). This is how we know which NOTFOUNDs to act on. Unmatched NOTFOUNDs are silently ignored, not punished.
Direction matters (sort of)
Both inbound and outbound peers can send GETDATAs and receive NOTFOUNDs. The protocol is symmetric. But Bitcoin Core's tx-download scheduler prefers outbound peers for actual requests, with shorter delays. So in practice we send more GETDATAs to outbound peers and therefore receive more NOTFOUNDs from them — but the handling is identical regardless of direction.
