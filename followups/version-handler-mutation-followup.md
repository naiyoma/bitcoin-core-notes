# Follow-up: VERSION handler mutation run (src/net_processing.cpp:3621-3854)

Run: bcore-mutation run_id=1, commit 610dd320, 2026-08-17.
DB: ~/Projects/bitcoin/mutation.db (tracked in git -- it FOLLOWS THE BRANCH,
currently on feature/mutate_net_processing_ProcessMessage_run_2).
Log: ~/mutation-run1-full.log
Report: ~/version-handler-mutation-report.md
Query tool: ~/bin/mutants-report <db> <run_id> [--survivors] [--commit=REV]

Result: 52 mutants, 36 killed, 14 survived, 2 equivalent, 0 timeouts.
Score 36/50 = 72%.

## Status as of 2026-08-19

Branch feature/mutate_net_processing_ProcessMessage_run_2, four commits, NONE COMPILED OR RUN YET.

| commit | file | kills | what |
|--------|------|-------|------|
| ffddfceb3a | src/test/denialofservice_tests.cpp | 47 | outbound handshake promotes the peer address new -> tried |
| fae12a7d8c | test/functional/p2p_leak.py | 34, 36 | peer at nVersion=70016 still gets WTXIDRELAY + SENDADDRV2 |
| 02cf53a70c | test/functional/p2p_sendtxrcncl.py | 38 | peer at nVersion=70016 still gets SENDTXRCNCL |
| 28b17a9818 | test/functional/p2p_leak.py | 12 | obsolete-version peer is disconnected by the version handler, not by the peer timeout |

Score if all four hold: 40/50 = 80% (from 36/50 = 72%).

### Verify before submitting anything

Each test must FAIL with its mutant applied. A test that passes either way is worthless here,
and two of these were written specifically because an existing test had that problem.

    cd ~/Projects/bitcoin
    for id in 47 34 36 38 12; do
      sqlite3 mutation.db "SELECT diff FROM mutants WHERE id=$id;" | git apply -
      cmake --build build -j4 --target bitcoind test_bitcoin >/dev/null
      echo "--- mutant $id: everything below must FAIL ---"
      ./build/bin/test_bitcoin --run_test=denialofservice_tests/version_handshake_promotes_outbound_addr_to_tried
      ./build/test/functional/p2p_leak.py
      ./build/test/functional/p2p_sendtxrcncl.py
      git restore src/net_processing.cpp
    done

Expected: 47 fails the unit test; 34/36 and 12 fail p2p_leak.py; 38 fails p2p_sendtxrcncl.py.
The mutant-12 failure should take ~60s (it is waiting out wait_for_disconnect); a fast failure
means something else broke.

Things most likely to need adjusting when first run:
- 28b17a9818 changed the asserted debug log from "peer=5" to "peer=0" because restart_node
  resets node ids. If the framework brings up a connection of its own during the restart the
  id shifts; dropping "peer=N" from the matched string still leaves a useful assertion.
- ffddfceb3a: if -checkaddrman is enabled in the build config, AddrMan::Add/Good run internal
  consistency checks that could fire before the test's own assertions.

### The mutant-12 finding (best PR material of the four)

p2p_leak.py already had this, and it looked airtight:

    with self.nodes[0].assert_debug_log(["using obsolete version 31799, disconnecting peer=5"]):
        p2p_old_peer.send_without_ping(self.create_old_version(31799))
        p2p_old_peer.wait_for_disconnect()

It passed with `pfrom.fDisconnect = true` mutated to `false`, for two reasons:
1. PEER_TIMEOUT = 3 (p2p_leak.py:32) -- the inactivity check reaps an undisconnected peer
   3 seconds later, and wait_for_disconnect() has a 60s window, so it cannot tell "disconnected
   for using an obsolete version" from "disconnected for being idle".
2. CNode::DisconnectMsg() (net.h:994) only formats a string; it does not read fDisconnect, so
   the asserted log line prints either way.

Line coverage showed :3663 as covered the whole time. Fixed by restarting with -peertimeout=999.

## Remaining survivors

| id | line | mutation | verdict |
|----|------|----------|---------|
| 16 | 3693 | `IsInboundConn() && addrMe.IsRoutable()` -> `\|\|` | OPTIONAL. nScore IS observable: getnetworkinfo localaddresses[].score (rpc/net.cpp:740). Needs -externalip to seed mapLocalHost with a routable address, since SeenLocal only increments entries that already exist (net.cpp:327). Score goes 4 -> 5 (LOCAL_MANUAL + SaturatingAdd), not 0 -> 1. Pattern: feature_bind_port_externalip.py, feature_bind_port_discover.py. |
| 17 | 3695 | delete `SeenLocal(addrMe);` | OPTIONAL. Same harness as 16; assert the score DOES increase for an inbound peer with a routable addrMe. |
| 3 | 3635 | `bool fRelay = true;` -> `false` | DECLINED. msg_version.serialize() (messages.py:1196) always appends the field; omitting it needs a subclass with no precedent. p2p_filter.py:241's `version_without_fRelay` is relay=0, an explicit false, NOT an omission. Impact further masked by `(fRelay \|\| NODE_BLOOM)` at :3725. |
| 21 | 3709 | `m_has_all_wanted_services = Has...()` -> `true` | DECLINED. Highest raw severity (feeds NodeEvictionCandidate.fRelevantServices, net.cpp:1711 -> eviction.cpp:34,52,197) but no RPC surface at all -- three references tree-wide. Unit-only, and no framing of the assertion was worth defending in review. |
| 29 | 3731 | `if (fRelay) m_relays_txs = true;` -> `false` | DECLINED. Same eviction machinery, same lack of surface. NOTE: CNode::m_relays_txs is NOT the field behind getpeerinfo.relaytxes -- that is Peer::TxRelay::m_relay_txs, set on the line above and reported via net_processing.cpp:1842. |
| 48 | 3838 | delete `m_outbound_time_offsets.Add(...)` | DECLINED. Observable via getnetworkinfo timeoffset/warnings, but Median() returns 0s below 5 samples (timeoffsets.cpp:38), so it needs 5+ outbound peers skewed past WARN_THRESHOLD (10 min). Payoff is a user-facing warning, not protocol behaviour. |
| 49 | 3839 | delete `.WarnIfOutOfSync()` | DECLINED. Same test as 48 would kill both. |
| 50 | 3843 | `<= 70012` -> `<` | NO. Legacy final-alert gate; <=70012 is pre-0.12 software. Accepted risk. |
| 51 | 3845 | delete alert send | NO. Same block. |

Equivalent, already reclassified in the DB: 4 (3638, nTime<0 -> <=, body assigns 0 either way)
and 28 (3729, `true ==> false` fired inside a `//` comment).

### If 16/17 get written, score reaches 43/50 = 86%.

## PR split

Do NOT submit from this branch: mutation.db is tracked here and the "test parallel runs" commit
(25206be9a2) must not travel with the tests. Cherry-pick onto a fresh branch off master.

- PR 1 "test: cover protocol version boundaries in the version handler" -- fae12a7d8c +
  02cf53a70c. Same finding (the WTXID_RELAY_VERSION boundary is never tested), two files.
- PR 2 -- 28b17a9818 alone. It is a FIX to an existing test, not new coverage, and reviews
  on its own merits: "this assertion is satisfied by the peer timeout regardless".
- PR 3 -- ffddfceb3a alone. Different subsystem (addrman), different reviewers.

Lead each description with the untested behaviour, not with mutation testing. Put the tool in
one line at the end, with the verification: "Verified by reverting <the line> and confirming
this test fails." That sentence is the most persuasive thing in a test PR.

## Reference: mutant 12 is at 3663, not 3656

Lines 3656 and 3663 are textually identical (`pfrom.fDisconnect = true;`).
3656 is the ExpectServicesFromConn() / HasAllDesirableServiceFlags() block and IS
covered by p2p_handshake.py::test_desirable_service_flags. 3663 is the
MIN_PEER_PROTO_VERSION block and is NOT covered. Verified by applying the patch
to a clean copy, not by reading the hunk header -- git does not always emit 3
lines of leading context, so hunk_start+3 is unreliable.

## Why mutants 21/29 survived despite eviction tests existing

- peerman_tests.cpp calls GetDesirableServiceFlags() directly -- tests the policy,
  never stores the result.
- net_peer_eviction_tests.cpp builds synthetic NodeEvictionCandidate structs
  (test/util/net.cpp:147 sets .fRelevantServices=randbool()) and does not include
  net_processing.h at all -- tests the consequence, never computes the value.
- The assignment at net_processing.cpp:3709 is the wire between them. Both ends
  are covered precisely because both bypass the middle.
- Neither m_has_all_wanted_services nor CNode::m_relays_txs has an RPC surface,
  so no functional test can observe them. Hence a unit test.
- NOTE: CNode::m_relays_txs (eviction only) is a DIFFERENT field from
  Peer::TxRelay::m_relay_txs (which does feed getpeerinfo.relaytxes via
  net_processing.cpp:1842). Do not conflate them.

## Tooling issues to report upstream to bcore-mutation

1. Timeouts are recorded as `killed`. analyze.rs:412-435 returns Ok(false) for
   both a timeout and a real failure; the 'timeout' status is never written. The
   distinction exists only in stdout, so ALWAYS pipe analyze through `tee`.
2. check_baseline() runs BEFORE the per-mutant restore_file(), so a dirty tree
   from a previous killed run makes the baseline test MUTATED code. Always
   `git restore src/net_processing.cpp` before starting.
3. Operators are regex over raw text with no comment stripping -- `true ==> false`
   fires inside `//` comments and produces guaranteed survivors (mutant 28).
4. The reported MUTATION SCORE does not exclude status='equivalent'.

## Operational notes for the next run

- Wrap the deadlock-prone stage: `timeout 150 ./build/bin/test_bitcoin ...`.
  Boost.Test has no internal time limit, so a handshake-breaking mutant hangs it
  forever. Functional tests self-limit via test_framework.py timeout_factor.
- Run functional tests FIRST, unit tests last, and pass --timeout generously
  (600) so the tool-level timeout never fires.
- Cleanup glob is /tmp/test_runner_* (test_runner.py), NOT /tmp/bitcoin_func_test_*
  (only used when a script is run directly).
- Consider adding p2p_eviction.py and net_peer_eviction_tests to the test set --
  neither was included. Note p2p_eviction.py would still not kill mutant 21: it
  has zero references to services and P2P_SERVICES defaults to
  NODE_NETWORK|NODE_WITNESS (test_framework/p2p.py:106), so every simulated peer
  already satisfies HasAllDesirableServiceFlags.
