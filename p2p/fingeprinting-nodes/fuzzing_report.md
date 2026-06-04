┌───────────────┬────────────────────────┬─────────────┬─────────────────────────┐
  │ node fuzz (W) │  analyst T=5s (fixed)  │ analyst T=W │ analyst T=2W (adaptive) │
  ├───────────────┼────────────────────────┼─────────────┼─────────────────────────┤
  │ ±5 seconds    │ 58% (real) / 75% (sim) │ 75%         │ 100%                    │                                                                                  
  ├───────────────┼────────────────────────┼─────────────┼─────────────────────────┤
  │ ±5 minutes    │ 1.8%                   │ 75%         │ 100%                    │
  ├───────────────┼────────────────────────┼─────────────┼─────────────────────────┤
  │ ±5 days       │ ~0%                    │ 75%         │ 100%                    │
  └───────────────┴────────────────────────┴─────────────┴─────────────────────────┘


The metric you're using is the wrong one (this is the "2f" answer)                         

  Your experiment measures the dual-homed pair in isolation: "did my pair's match % drop." But that's not the decision the attacker makes. The attacker runs a classifier: given two
  getaddr responses, decide "same node" vs "two unrelated nodes." The defense succeeds when your dual-homed pair becomes statistically indistinguishable from a random pair of unrelated
  nodes that happen to share peers — not when exact-match fails.                             
                                                                                             
  That reframing dissolves the "2f" worry:

  - Yes, widening the window to 2×jitter recovers your true matches. Always will.            
  - But widening the window also inflates matches against unrelated nodes. The attacker only wins if, at the window where they recover your pair, your pair still scores above the 
  unrelated baseline.                                                                        
  - So the real question is never "what jitter makes exact match fail" — it's "what jitter makes my pair's timestamp-diff distribution look like the unrelated-pair distribution."

  Your experiment has no control group, so it literally cannot tell you whether correlation is broken. You need to crawl a bunch of unrelated node pairs (your crawler already sweeps
  the network) and build the baseline distribution of timestamp diffs for coincidentally-shared peers. That baseline is your target to blend into.

  Why seconds/minutes can't work and days can

  The signal the attacker exploits: a dual-homed node's two responses come from one AddrMan, so a shared peer has the same nTime in both → diff ≈ 0. Two unrelated nodes
  learned/refreshed that same peer independently, so their nTimes differ by the natural inter-node spread — hours to days.

  So the discriminator is: true pair → diffs clustered near 0; unrelated pair → diffs spread wide. To erase it, your jitter spread has to be on the same order as that natural spread.
  ±5s vs a natural spread of hours-to-days is why the ±10s window still nails you at 100%. This — not "5s breaks exact match" — is the actual justification for going to the days scale.
  You can measure the natural spread from your crawl and size the jitter to it; you don't have to guess.
 
  Your "older not newer" instinct is right — here are the exact thresholds                   

  I confirmed the receiver-side logic in net_processing.cpp:5685–5709 and addrman:           

  - Relay cutoff (line 5695): an incoming addr is gossiped onward only if nTime > current_time - 10min. So anything you age past 10 minutes will not be re-relayed by the receiver. Good
  — aging avoids artificially refreshing gossip.
  - Future clamp (line 5685): if nTime > current_time + 10min, the receiver resets it to current_time - 5*24h. So never fuzz into the future — it gets clobbered (and would be a tell).
  - Horizon (addrman.h:29, ADDRMAN_HORIZON = 30*24h): past 30 days IsTerrible() is true → the addr won't be selected for connection and loses bucket-collision evictions. Not harmful,
  just dead weight.                                                                          

  So the safe aging window is (10 minutes, 30 days). Your 10.5 ± 2.5 days (8–13d) sits cleanly inside it. Making timestamps newer is bad exactly as you said: pull within 10 min of now
  and you've turned the node into a gossip-refresher for stale addresses.

A real bug in your current patch vs. your comment                                          

  Your code adds per-address ±5s jitter, but the comment describes a different design — "set the timestamps for each cache to a fixed time in the past." Those disagree, and the
  fixed-time design is actually worse:

  - If cache A sets every addr to T_A and cache B to T_B, then every shared peer has diff = |T_A − T_B|, a constant. "All shared peers have identical diff" is a glaring fingerprint —
  trivially detectable and screams "patched node."
  - Per-address independent jitter is the right primitive. The only fix needed is magnitude (days, sized to the measured baseline), not switching to a fixed value.

  One caveat even for large jitter: jitter around the true value preserves ordering (a fresher peer stays probably-fresher in both caches), so a sophisticated attacker can use rank
  correlation. Killing that fully means collapsing structure, which fights against not-being-a-fingerprint. There's tension here with no perfect answer (see last section).

  Use Python — you're right, stop recompiling                                                

  Correct instinct. The transform is a pure function of (peer_addr, nTime), so:              
 
  1. Capture raw unfuzzed responses once from both interfaces.                               
  2. Capture responses from many unrelated pairs → build the baseline diff distribution.
  3. In Python, apply candidate transforms to the captured nTimes and recompute a discrimination score — not match %, but something like KS-distance or a likelihood ratio between your
  pair's diff distribution and the unrelated baseline. Sweep s → min → hours → days.         
  4. Pick the smallest range where your pair falls inside the baseline's noise band.         

  Only rebuild Core once, to deploy the winner.                                              

 Other fuzzing in the codebase — no, it's not the same thing                                

  I checked. None of the other randomization serves this purpose, so there's no precedent and no shared "2f" exposure:

  - 21h + randrange(6h) cache expiration (net.cpp) — cache lifetime jitter, not a per-address value compared across responses.
  - 10min + randrange(5min) (net_processing.cpp:1640,2036) — addr broadcast timer jitter (Poisson-ish send timing).
  - current_time - 5*24h reset and time_penalty=2h on Add — normalizations, not privacy fuzz.

  This GetAddresses spot is the only place doing timestamp-correlation defense, which is why you're inventing the approach rather than copying one.

  The honest ceiling                                                                         
 
  You sensed this already ("from a broader perspective…"). There is probably no timestamp transform that perfectly defeats a determined statistical attacker, because both responses
  provably derive from one AddrMan and the peer-set overlap itself already leaks — timestamps are only a secondary amplifier. But the realistic and worthwhile goal is to degrade the 
  timestamp channel until it's no more informative than the set-overlap channel — and per the Delving post, overlap alone is weak when thousands of honest nodes share the same limited
  peer pool. That drops the attacker from certain (your 100%) to merely suspicious. That's a genuine privacy win, and it's the right bar to aim for — not 0%.

  