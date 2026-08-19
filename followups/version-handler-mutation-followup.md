# Follow-up: VERSION handler mutation run (src/net_processing.cpp:3621-3854)

Run: bcore-mutation run_id=1, commit 610dd320, 2026-08-17.
DB: ~/Projects/bitcoin/mutation.db (tracked in git -- it FOLLOWS THE BRANCH,
currently on feature/mutate_net_processing_ProcessMessage_run_2).
Log: ~/mutation-run1-full.log
Report: ~/version-handler-mutation-report.md
Query tool: ~/bin/mutants-report <db> <run_id> [--survivors] [--commit=REV]

Result: 52 mutants, 36 killed, 14 survived, 2 equivalent, 0 timeouts.
Score 36/50 = 72%.

## Done

- [x] mutant 21 + 29 -- unit test `version_records_service_and_relay_state`
      added to src/test/denialofservice_tests.cpp. NOT YET COMPILED OR RUN.

## Next: verify the new test

    cmake --build build -j4 --target test_bitcoin
    ./build/bin/test_bitcoin --run_test=denialofservice_tests/version_records_service_and_relay_state

Then confirm it actually kills the mutants (this is the point -- a test that
passes but does not kill is worthless here):

    cd ~/Projects/bitcoin
    sqlite3 mutation.db "UPDATE mutants SET status='pending' WHERE id IN (21,29);"
    ~/bin/mutants-report mutation.db 1 --survivors --commit=610dd320
    # re-run analyze with --survivors_only and check 21 and 29 flip to killed

## Remaining survivors, in priority order

| rank | id | line | mutation | test to write | type |
|------|----|------|----------|---------------|------|
| 1 | 47 | 3831 | delete `m_addrman.Good(pfrom.addr);` | outbound handshake completes -> assert addr moved New->Tried. rpc_net.py ALREADY calls getrawaddrman, just needs the assertion. Cheapest high-value test. | functional |
| 2 | 34 | 3751 | `>= WTXID_RELAY_VERSION` -> `>` | one test: VERSION with nVersion=70016, assert WTXIDRELAY + SENDADDRV2 + SENDTXRCNCL all still sent. Kills all three. | functional |
| 2 | 36 | 3756 | `>= 70016` -> `>` | (same test) | functional |
| 2 | 38 | 3764 | `>= WTXID_RELAY_VERSION && m_txreconciliation` -> `>` | (same test) | functional |
| 3 | 3 | 3635 | `bool fRelay = true;` -> `false` | VERSION with the trailing fRelay field OMITTED -> assert getpeerinfo.relaytxes | functional |
| 4 | 12 | 3663 | `pfrom.fDisconnect = true;` -> `false` | peer with nVersion < MIN_PEER_PROTO_VERSION (31800) -> assert disconnect | functional |
| 5 | 48 | 3838 | delete `m_outbound_time_offsets.Add(...)` | 5+ outbound peers with timestamps skewed >10min -> assert getnetworkinfo.timeoffset | functional |
| 5 | 49 | 3839 | delete `.WarnIfOutOfSync()` | (same test) -> assert getnetworkinfo.warnings | functional |
| 6 | 16 | 3693 | `IsInboundConn() && addrMe.IsRoutable()` -> `\|\|` | SeenLocal scoring: inbound routable vs outbound vs unroutable | unit |
| 6 | 17 | 3695 | delete `SeenLocal(addrMe);` | (same test) | unit |
| -- | 50 | 3843 | `<= 70012` -> `<` | DO NOT TEST -- legacy final-alert path, pre-0.12 peers. Accepted risk. | -- |
| -- | 51 | 3845 | delete alert send | DO NOT TEST -- same block. Accepted risk. | -- |

Reclassified equivalent (already updated in the DB):
- id 4  (3638) `nTime < 0` -> `<=`  : body assigns nTime=0, differs only at nTime==0 assigning 0 to 0.
- id 28 (3729) comment-only        : `true ==> false` fired inside a `//` comment. Tool bug.

## Why mutant 12 is NOT the desirable-services block

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
