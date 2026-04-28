

1. is i noticed that if the runs fast , this is not always the case but it happens sometimes 
the blcoks are identical 
2026-04-28T16:57:11.513220Z TestFramework (INFO): Create a second block at height 2 (will be stale)
2026-04-28T16:57:11.513768Z TestFramework (INFO): First block hash:  02feedace670d3333442c220cce3e501e2389b9c1826b68fb860500486637f1e
2026-04-28T16:57:11.514050Z TestFramework (INFO): Stale block hash:  02feedace670d3333442c220cce3e501e2389b9c1826b68fb860500486637f1e
2026-04-28T16:57:11.514317Z TestFramework (INFO): Blocks are identical: True

i did log 
this condition 
received_new_header=0 is zero

in windows where the test is failign is because 
when we have 

so when the te

I think ive been able to recreate the ci failure 
the test was inteminateky timing out dependign on how past the test was rinning 
when run time becomes slight slower then the 
this wpuld time out 
and thats because the when the test would run fast the blcoks created would be identical 
and then when the test would be slow timestmaps would be different so blocks would also be different 

i think ive been been able to recreate the ci failure 
the test seems to pass immediatley and the timeout is dependent on how fast the test is running
when the test is runign fast block and block 2 is similary 
so 
blocks[-1].hash_hex == node.getbestblockhash() is immediately True

when the test is slow block and block2 are completely different and with equal chainwork
block2.hash_hex == block.hash_hex is False
wait_until keeps polling for 60 seconds waiting for the tip to change
Timeout after 60 seconds

Another issue i relaized is that the test doesnt not create a new header so even when the
test was pasing it was its because 
received_new_header=0

i think this should work, new a new header and for the blcoks to have different chainwork
+        headers_message2 = msg_headers()
+        headers_message2.headers = [CBlockHeader(block2)]
+        peer.send_and_ping(headers_message2)
+        node.getblockheader(node.getbestblockhash())['chainwork']
 
last_header.nChainWork=0000000000000000000000000000000000000000000000000000000000000006 tip->nChainWork=0000000000000000000000000000000000000000000000000000000000000006 received_new_header=1

void PeerManagerImpl::UpdatePeerStateForReceivedHeaders(CNode& pfrom, Peer& peer,
        const CBlockIndex& last_header, bool received_new_header, bool may_have_more_headers)
{
    LOCK(cs_main);
    CNodeState *nodestate = State(pfrom.GetId());

    UpdateBlockAvailability(pfrom.GetId(), last_header.GetBlockHash());

    // From here, pindexBestKnownBlock should be guaranteed to be non-null,
    // because it is set in UpdateBlockAvailability. Some nullptr checks
    // are still present, however, as belt-and-suspenders.
    LogDebug(BCLog::NET, "UpdatePeerStateForReceivedHeaders: last_header.nChainWork=%s tip->nChainWork=%s received_new_header=%d\n",
         last_header.nChainWork.GetHex(),
         m_chainman.ActiveChain().Tip()->nChainWork.GetHex(),
         received_new_header);

    if (received_new_header && last_header.nChainWork > m_chainman.ActiveChain().Tip()->nChainWork) {
            LogDebug(BCLog::NET, "UpdatePeerStateForReceivedHeaders: updating m_last_block_announcement\n");

        nodestate->m_last_block_announcement = Now<NodeSeconds>();

    }


