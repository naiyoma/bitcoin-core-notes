# bcore-mutation `--parallel`: benchmark, correctness, and review findings

Evaluation of the `--parallel` feature (`pr-parallel`, commit `9806580`) across
two machines and three configurations, plus defects found while running it.
2026-09-04 → 2026-09-07.

**Headline:** the feature is correct and it is fast enough to matter, but
whether it pays off is decided by one ratio — setup cost over per-mutant cost.
On one machine parallel lost by 23%; on another it won by 37%. The same formula
predicts both.

## Summary

I compared per-mutant analysis time between the normal (non-parallel) run and
`--parallel`, on the same mutant set, same machine, same test command.

The version and verack message handlers are contiguous in `net_processing.cpp`,
so I generated them as **one range instead of two** and got 68 mutants.
Analyzing both together under `--parallel` took less time than analyzing each
separately without it, and produced identical verdicts. I then extended the
range across ten handlers (VERSION → INV) for 127 mutants.

My takeaway: **merging batches of mutants and running them in parallel saves
time, and the two compound.** Setup is paid once per invocation, so twelve
per-handler runs pay it twelve times while halving less work each time. One
combined run pays it once and amortizes it across the whole set. Below ~13–16
mutants on this hardware the setup tax still exceeds the saving and the plain
run wins.

---

## Results

| | laptop | neo50t — run A | neo50t — run B |
|---|---|---|---|
| CPU / RAM | 8 cores / 15 GB | 28 cores / 6.9 GB | 28 cores / 6.9 GB |
| ccache | 5 GB, 43% hits | **not installed** | **not installed** |
| Mutants | 16 | 68 | **127** |
| Range | 4075–4155 | 3833–4154 (VERSION+VERACK) | 3833–4437 (10 handlers) |
| Test command | `test_bitcoin` only | 23 functional + 6 unit | 34 functional + 7 unit |
| Config | `--parallel 2 --jobs 4` | `--parallel 2 --jobs 2` | `--parallel 2 --jobs 2` |
| **Setup `S`** | **36 min** | **14 min** | **14 min** *(reproduced exactly)* |
| **Per-mutant `t`** | 2.9 min *(derived)* | 1.73 min *(measured)* | 2.19 min *(derived)* |
| **Parallel total** | **59:18** | **1:16:06** | **2:38:13** |
| **Non-parallel total** | ~48 min *(projected)* | **1:59:43** *(measured)* | ~4h43m *(predicted)* |
| Crossover `M*` | ~25 mutants | ~16 mutants | **~13 mutants** |
| Mutants vs crossover | 16 → **below** | 68 → 4.3× above | 127 → **10× above** |
| **Winner** | **non-parallel**, by ~11 min | **parallel, 1.57×** | **parallel, ~1.79×** *(predicted)* |
| Score | 25% (4/16) | 67.65% (46/68) | **75.59% (96/127)** |
| Kills that were timeouts | **3 of 4** | 0 of 46 | **0 of 96** |

Runs A and B used different test commands, so their `t` values are not
comparable — treat them as two configurations, not two points on one curve.
`S` was **14 min in both**, confirming setup is a fixed cost independent of
batch size and test command.

The laptop's 25% is mostly artifact: only one of its four kills was a real test
failure, so the honest score there is 6.25%. Both neo50t scores are genuine —
zero timeout kills.

---

## Correctness

### Verdict parity — per mutant, not just totals

Run A analyzed the identical 68 mutants in both modes. Joined on `patch_hash`:

```
same mutant set:        68 / 68 / 68 matched
verdict disagreements:  0
```

**Every individual mutant received the identical verdict in both modes.**
Matching totals (46 killed / 22 survived) would have been weaker — two runs can
each kill 46 *different* mutants. Zero disagreements is the real result.

Worker isolation — separate worktrees, per-worker `TMPDIR`, disjoint
functional-test port ranges — holds under 23 concurrent functional tests plus 6
unit suites. **`--parallel` changes speed, not results.**

### Nothing is skipped

Run B, 127 mutants:

```
generated (pre-run snapshot): 127
analyzed: 96 killed + 31 survived = 127
pending: 0    running: 0    error: 0
```

Every dispatched mutant received a verdict.

### Combined run vs twelve individual per-handler runs

The same handlers had previously been analyzed one at a time, each with its own
narrow test command (committed on `feature/mutate_net_processing_ProcessMessage`,
runs 1–9 and 12). Comparing them to the single combined run:

| | individual | combined |
|---|---:|---:|
| Wall clock | **6–7 h** (to reach INV) | **2:38:13** |
| Mutants | 123 | 127 |
| Killed | 74 | **96** |
| Survived | 49 | 31 |
| **Score** | **60.2%** | **75.59%** |

Matched by mutation content (119 of them), verdict transitions were:

| individual → combined | count |
|---|---:|
| killed → killed | 71 |
| survived → survived | 28 |
| **survived → killed** | **20** |
| **killed → survived** | **0** ← nothing regressed |

**Not one mutant lost its kill.** The combined run caught 20 the per-handler
runs missed, because each mutant faced the union of all tests rather than only
its own handler's. Deleting the VERACK send, deleting `m_addrman.SetServices`,
`fDisconnect = true → false` — all survive a handshake-only suite and die once
addr-relay and tx-download tests run.

Of 4 mutations initially unmatched, 3 were false alarms — present in the
combined run under different context lines, since the surrounding code changed
between commits. Exactly **one** is genuinely absent: `if (msg_type ==
NetMsgType::VERSION)` → `!=`. That is a *generation* artifact, not a
parallelism one: line 3833 produced no mutant in the combined run at all
(its lowest is 3834), because `--one-mutant` picks one operator per line and
the two generations chose differently. It would have been killed regardless.

**Conclusion: ~2 hours versus 6–7, with strictly better detection and no
regressions.**

#### Worked example — why per-handler test selection misses bugs

Mutant 45 of the individual VERSION run, in the outbound-connection branch of
the VERSION handler:

```diff
             // We skip this for block-relay-only peers. We want to avoid
             // potentially leaking addr information and we do not want to
             // indicate to the peer that we will participate in addr relay.
-            MakeAndPushMessage(pfrom, NetMsgType::GETADDR);
+
             peer.m_getaddr_sent = true;
```

The node stops asking new peers for addresses, while still setting
`m_getaddr_sent = true` so it believes it asked. A node running this would
slowly starve its addrman of fresh peers.

**Individual run — survived.** Its command was:

```
test_bitcoin --run_test=denialofservice_tests,peerman_tests,net_tests
  && p2p_handshake.py && p2p_leak.py && p2p_timeouts.py
  && p2p_v2_transport.py && p2p_permissions.py && feature_proxy.py
```

All six functional tests check that the *handshake completes* — version/verack
exchange, disconnects, timeouts, permissions, proxy. None asserts that a GETADDR
is sent. The handshake succeeds with the line deleted, so every test passes.

**Combined run — killed.** It also ran `p2p_addr_relay.py`, `p2p_addrfetch.py`,
`p2p_addr_selfannouncement.py`, `feature_addrman.py` and
`p2p_getaddr_caching.py`, which assert on address solicitation directly.
`p2p_addr_relay` expects a GETADDR after connecting; with the send removed that
expectation fails.

**The general lesson:** the mutation is *in* the VERSION handler, so
handler-based test selection assigns it VERSION's tests — but its observable
effect is in **address relay**, a different subsystem. Any selection strategy
keyed to where code lives rather than what it affects will miss it. Its
neighbour, mutant 46 (`m_getaddr_sent = true → false`), is the same story one
line down.

This is why merging handlers into one run is not only ~3× faster but **more
correct**: cross-subsystem effects only surface when the tests that observe
them actually run.

### Score by handler (run B)

| Handler | Mutants | Killed | Survived | Score |
|---|---:|---:|---:|---:|
| VERSION | 55 | 37 | **18** | 67% |
| VERACK | 16 | 13 | 3 | 81% |
| SENDCMPCT | 8 | 7 | 1 | 88% |
| WTXIDRELAY | 6 | 4 | 2 | 67% |
| SENDADDRV2 | 4 | 4 | 0 | **100%** |
| FEATURE | 6 | 6 | 0 | **100%** |
| SENDTXRCNCL | 13 | 11 | 2 | 85% |
| ADDR/ADDRV2 | 4 | 3 | 1 | 75% |
| INV | 15 | 11 | 4 | 73% |

VERSION holds 18 of the 31 survivors. Recurring gaps: six version-boundary
comparisons (`>=` → `>` on `WTXID_RELAY_VERSION`, `70016`, `70012`,
`SHORT_IDS_BLOCKS_VERSION`) survive because no test connects at exactly the
boundary; five deletable statements nothing observes (`SeenLocal`,
`m_addrman.Good`, `m_outbound_time_offsets.Add`/`WarnIfOutOfSync`,
`AddKnownTx`); and `fDisconnect = true → false` survives in three separate
handlers. Full list in `survivors-127.txt`.

---

## The formula

Parallel wins when the analysis time it saves exceeds the setup it adds:

```
t × M × (1 − 1/N)  >  S
```

Break-even batch size:

```
M* = S / (t × (1 − 1/N))

laptop:  36 / (2.9  × 0.5) ≈ 25 mutants
run A:   14 / (1.73 × 0.5) ≈ 16 mutants
run B:   14 / (2.19 × 0.5) ≈ 13 mutants
```

`M*` is **not a property of the tool.** It is the ratio of setup cost to
per-mutant cost, and it moves with hardware, ccache, and the test command:

- **Cheaper test command** → `t` drops, `S` unchanged → `M*` rises
- **Slower test command** (functional tests, fuzz) → `t` rises → `M*` falls
- **Faster machine / warm ccache** → `S` drops → `M*` falls
- **More workers** → `(1 − 1/N)` grows, but `S` grows too, since N cold builds
  contend for the same cores and RAM. Re-measure; do not extrapolate.

---

## Crossover tables

### laptop — 8 cores, 15 GB, `S`=36, `t`=2.9

| Mutants | non-parallel | parallel (N=2) | winner | status |
|---:|---:|---:|---|---|
| 3 | 9 min | 40 min | non-parallel, by 4× | projected |
| 16 | 46 min | **59 min** | non-parallel | **parallel measured** |
| 25 | 73 min | 72 min | tie — crossover | projected |
| 100 | 290 min | 181 min | parallel, saves ~2 h | projected |

### run A — 68 mutants, 23-test command, `S`=14, `t`=1.73

Fitted to the two measured endpoints at M=68:

```
non-parallel = 2  + 1.731 × M
parallel     = 16 + 0.884 × M
```

The parallel slope is 0.884 against an ideal 0.866 — that 2% gap is the
scheduler's entire overhead.

| Mutants | non-parallel | parallel (N=2) | saves | winner |
|---:|---:|---:|---:|---|
| 8 | 16 min | 23 min | −7 min | non-parallel *(projected)* |
| 16 | 30 min | 30 min | 0 min | tie — **crossover** *(projected)* |
| 68 | **119:43** | **76:06** | **43.6 min** | **parallel, 1.57×** *(both measured)* |

### run B — 127 mutants, 34-test command, `S`=14, `t`=2.19

| Mutants | non-parallel | parallel (N=2) | saves | winner |
|---:|---:|---:|---:|---|
| 13 | 33 min | 33 min | 0 min | tie — **crossover** *(projected)* |
| 68 | 154 min | 94 min | 60 min | parallel, 1.64× *(projected)* |
| 127 | ~4h43m *(predicted)* | **2:38:13** | ~2h05m | **parallel, ~1.79×** *(parallel measured)* |

The more mutants, the more time parallel saves: setup is fixed, only per-mutant
work is halved, so the saving grows while the tax stays flat. Speedup
approaches but never reaches 2×.

### Model accuracy

| Run | Predicted | Actual | Error |
|---|---:|---:|---:|
| laptop, parallel, 16 mutants | 59.2 min | **59:18** | 0.2% |
| neo50t, non-parallel, 68 mutants | 122 min | **119:43** | 1.9% |

Both predictions were recorded before the runs finished.

### Scheduling efficiency

Non-parallel spent ~117.7 min on mutants; parallel did the same work in ~60 min
across 2 workers, against a 58.9 min floor — **98% efficient**. All of
parallel's disadvantage at small batches comes from setup, none from the
scheduler.

### Per-mutant cost tracks the kill rate

`--failfast` makes a killed mutant exit on its first failing test while a
survivor runs everything, so `t` depends on the kill rate, not the test list
alone:

| | run A (68) | run B (127) |
|---|---:|---:|
| kill rate | 68% | 76% |
| survivor cost | ~2.5 min | ~4.5 min |
| kill cost | ~1.3 min | ~1.4 min |
| **average `t`** | 1.73 min | 2.19 min |

Run B used a 48% longer test list for only 27% higher average cost. Estimating
runtime from a dry run on unmutated code **overestimates** it — the dry run
always pays the survivor price. (My own estimate for run B was 4.5 h against an
actual 2:38 for exactly this reason.)

---

## Findings

| # | Finding | Evidence |
|---|---|---|
| 1 | Worker root is created in the system temp dir with **no free-space check** | neo50t `/tmp` is a 3.5 GB tmpfs; setup died at 6:33 with `No space left on device` **while `/` had 412 GB free** |
| 2 | **No flag to relocate the worker root** | only fixable by `export TMPDIR=...` before launching |
| 3 | `ENOSPC`/`EDQUOT` surfaces as a generic failure | `setup command failed in worker 0 (exit code 2)`; real cause only visible by reading compiler output |
| 4 | Setup timeout **hardcoded at 3600s**, no CLI flag | `src/commands.rs:23` — killed the first laptop run |
| 5 | **Timeouts are scored as `killed`** | `src/parallel.rs:938` — `execution.timed_out` computed and ignored. Inflated the laptop score from 6.25% to 25% |
| 6 | `'timeout'` status exists in the schema, written by no code path | `src/db.rs:37` (`'equivalent'` is likewise unused) |
| 7 | Baseline uses the **per-mutant** `--timeout`, not its own budget | both paths; a baseline is a full build-and-test, structurally like setup |
| 8 | **README never mentions RAM** | it warns about CPUs, disk and ports only. Its own example `--parallel 3 --jobs 4` = 12 jobs × 1.68 GB ≈ **20 GB**, impossible on a 6.9 GB box |
| 9 | **Crossover is undocumented** | no mention of when parallel is worth using; a reader has every fact and no way to assemble them |
| 10 | `config_json` records only the line range | not `--one-mutant` or other generation flags, so runs are not reproducible from the DB |
| 11 | **`patch_hash` is position-dependent** | `sha256(unified diff)` embeds hunk line numbers *and* the `index <blob>..<blob>` line, so the same mutation hashes differently after any file change — runs cannot be compared across commits. Hashing the hunk body without `@@`/`index` lines fixes it (~15 lines) |

### Retracted

- ~~"The sequential path runs no baseline check"~~ — **wrong.** `check_baseline`
  is at `src/analyze.rs:547` and runs on both paths.

### The sharpest one

Findings 4 and 8 interact badly. On neo50t the 60-minute setup cap sits *below*
the crossover, so the tool can only complete a parallel run in the regime where
parallel wins — if setup were slow enough for parallel to lose, the run would
die rather than report it.

The root cause of the crossover itself is that **setup performs N full cold
builds of identical source, concurrently, in lockstep.** Building once and
cloning the tree into each worker would collapse `S` toward zero and take `M*`
with it, making findings 8 and 9 largely moot.

---

## Method

Controls held constant between arms:

- identical mutant set — DB snapshotted with `.backup`, `.restore`d between arms
- identical `-c` command string and `--timeout`
- same machine, same `TMPDIR`, arms run **sequentially** — never concurrently,
  since `port_floor_for(0)` is 11000, exactly the default functional-test
  `PORT_MIN`, so simultaneous arms collide on ports
- equal total job budget: non-parallel `1 × N`, parallel `2 × N/2`
- non-parallel uses the pre-existing warm `build/`; parallel pays
  `--setup-command`. That asymmetry **is** the thing being measured.

Job budget was set by RAM, not cores: `-j` × 1.68 GB per Bitcoin Core
translation unit (measured) must fit in available memory. On neo50t that is 3
jobs despite 28 cores.

Generation: `bcore-mutation mutate --sqlite --one-mutant -f
src/net_processing.cpp --range 3833 4437`.

Cross-commit comparison used a content key — the hunk body with context lines,
excluding the `@@` header and `index` line — because `patch_hash` is
position-dependent (finding 11). Validated 1:1 against raw counts:
123 mutants → 123 unique keys, 49 survivors → 49.

## Caveats

1. The laptop's non-parallel arm was **never run** — derived from per-mutant
   costs measured during its parallel run.
2. Laptop `t` is a lower bound: its three timeout kills are censored at 300s.
3. Run B's non-parallel arm was not run; its 1.79× is predicted, not measured.
   Run A is the fully-measured pair.
4. neo50t has no ccache, so both arms build fully cold. This inflates `S` and
   understates parallel relative to a developer machine with a warm cache.
5. The individual per-handler runs were each at a different commit and used
   narrower test commands, so the 60.2% vs 75.59% comparison reflects test
   coverage, not tool behaviour.

## Artifacts

| File | Contents |
|---|---|
| `survivors-127.txt` | the 31 survivors of run B, by handler, with mutations |
| `survivors-individual.txt` | the 49 survivors of the per-handler runs |
| `mutation.db.neo127` | run B results (127 mutants) |
| `mutation.db.parallel` / `.nonparallel` | run A arms — the parity check |
| `mutation.db.clean127` | run B pre-run snapshot |
