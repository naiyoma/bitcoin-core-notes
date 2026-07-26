Test issues 	
Whilelist[6] this is not being used anywhere  (rpc whitlist default)	
in last_block_announcement test that cmpt block also update this last_announcment 	
in self announcement we should test that we actally do relay a getaddr that is small 	
Write a unit test for this -> https://github.com/bitcoin/bitcoin/issues/28635	(MAX_ADDNODE_CONNECTION )
i have noticed that theres no functional test for this warning -> in init.cpp  InitWarning(strprintf(_("More than one onion bind address is provided. Using	

The genuine gap is the FALSE branch of IsAddrCompatible: confirming that a peer which did not negotiate addrv2 (v1-only) is excluded from receiving an addrv2-only address
(I2P/TorV3). No test connects a v1-only receiver alongside the addrv2 one and asserts it gets zero of the I2P/onion addrs. That's the line that proves the || short-circuit actually
filters, rather than just verifying it lets things through

look into 
https://github.com/bitcoin/bitcoin/pull/30713/changes

this is random tou can look at this later on 
1. net_processing:5689 IsDiscouraged || IsBanned → && — banned addr leaks into relay/storage. Security. 1 test (setban + assert not relayed).
 if (m_banman && (m_banman->IsDiscouraged(addr) || m_banman->IsBanned(addr)))
 check that a banned or discuraged addresses are not relayed 
 we use the rpc setban to ban an address 
2. eviction:33 + :51 — 4 mutants (!=→1==1 ×2, <→<= ×2). Equal-m_last_block_time tie path; <= is std::sort UB in the common prod case. One test kills all 4 + unlocks the 34/35/52/53
  fall-through.
3. net_processing:2921 + 4537 — 6 mutants (>→<,>=,<=; &&→|| per site). last_block_announcement write path, zero unit coverage; affects which extra-outbound peer gets evicted. 1 unit test per site.
4. net_processing:5682 !MayHaveUsefulAddressDB && !HasAllDesirableServiceFlags → || — send NODE_NETWORK_LIMITED-only addr, assert processed.
5. eviction:197 !m_relay_txs && fRelevantServices → || — add a relay-txs + relevant-services peer.
6. net_processing:5685 nTime <= 1e8s || > now+10min → </>=/&& — timestamp clamp; low consequence, awkward assert.
7. net_processing:5695 inner (size<=10 && IsRoutable) && → ||
8. net_processing:5700 if(reachable) store → negate
9. net_processing:2288 !fReachable && !IsRelayable() → ||
10. net_processing:1133 IsValid() && !contains() && IsAddrCompatible → ||


in p2p_addr_relay.py
check that we do not relay banned or discouraged address / once unbanned we can relay
i will also use the is banned helper here 

in rpc_setban.py
use the shared helper here 
check that the other two fields in listbann rpc are being tested 
The point I was making: the tests assert ban_duration (rpc_setban.py:84, p2p_disconnect_ban.py:95) and time_remaining (p2p_disconnect_ban.py:96), but nothing ever asserts ban_created
or banned_until. If a bug made ban_created return garbage, no test would catch it. That's the "missing field coverage.

Refactor p2p_disconnect_ban.py 
theres a redudant comment here 
comment + index→membership checks.
1. Line 58 comment is wrong about why the count stays 1.                                                                                                                              
  57  assert_raises_rpc_error(-30, "Error: Invalid IP/Subnet", self.nodes[1].setban, "127.0.0.1/42", "add")                                                                             
  58  assert_equal(len(self.nodes[1].listbanned()), 1)  # still only one banned ip because 127.0.0.1 is within the range of 127.0.0.0/24                                                
  The count stays 1 because /42 is an invalid IPv4 prefix (max is /32), so the setban is rejected outright with error -30. It has nothing to do with range containment. The             
  range-containment logic is actually what's tested on line 54 ("IP/Subnet already banned"). The comment on line 58 borrows line 54's reasoning and applies it to an unrelated          
  invalid-input case.                                                                                                                                                                                                                                                                                                                                                 
  2. Lines 83 / 109–113 assert on banlist ordering by numeric index.                                                                                                                    
  83   assert_equal("192.168.0.1/32", listBeforeShutdown[2]['address'])                                                                                                                 
  109  assert_equal("127.0.0.0/24", listAfterShutdown[0]['address'])                                                                                                                    
  These couple the test to listbanned()'s internal sort order — and notice the order changes across restart (before: 192.168.0.1 at index 2; after: a completely different arrangement).
  That's not an "inaccuracy" exactly, but it's fragile, implementation-coupled, and obscures intent. Asserting membership (like rpc_setban.py's is_banned() helper) would be more       
  honest.                                                                                                                                                                               
                                                                                                                                                                                        
  3. Line 77 bans 127.0.0.0/32 — the network address, redundant with the /24 already in play — which is what forces the odd index gymnastics later. Minor, but it reads as accidental.



in p2p_addr_relay.py 
check that we don't relay banned or discouraged addresses 
use setban to ban an address and then have one address that is misbehaving
and then have an address that is normal and oly check that one address is being relayed 
send addr with out-of-range nTime; assert stored time was clamped (via getnodeaddresses)
send a reachable addr via p2p; assert getnodeaddresses returns it (survived feature_addrman, so needs an explicit assertion)
craft addrs with partial service flags; assert the filter drops the right one and a valid addr after a filtered one still processes (kills
the continue→break)
send exactly MAX_ADDR_TO_SEND (1000) addrs; assert no misbehaving (existing test sends 1010, missing the boundary)
exactly-1000 boundary on m_getaddr_sent; low value, do last               for each and every on this tier 2 they are nice haves but not 

in rpc_setban.py 
make sure that after ban time is over that the ip address is no longer banned 

