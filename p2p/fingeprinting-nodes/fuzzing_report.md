┌───────────────┬────────────────────────┬─────────────┬─────────────────────────┐
  │ node fuzz (W) │  analyst T=5s (fixed)  │ analyst T=W │ analyst T=2W (adaptive) │
  ├───────────────┼────────────────────────┼─────────────┼─────────────────────────┤
  │ ±5 seconds    │ 58% (real) / 75% (sim) │ 75%         │ 100%                    │                                                                                  
  ├───────────────┼────────────────────────┼─────────────┼─────────────────────────┤
  │ ±5 minutes    │ 1.8%                   │ 75%         │ 100%                    │
  ├───────────────┼────────────────────────┼─────────────┼─────────────────────────┤
  │ ±5 days       │ ~0%                    │ 75%         │ 100%                    │
  └───────────────┴────────────────────────┴─────────────┴─────────────────────────┘


so i repeated the experiment with my own node 

matching peers between my ipv4 and tor connection

48 peers
out of those 48 peers 
they all shared the same exact timestamp
so my match percentage is 100%

1. fuzzed with +/-5 seconds 
correlation reduced to 58%

2. fuzzed with +/-5 minutes
correlation reduced to 1.8

3. fuzzed with +/-5 days 
correlation reduced to 0%

note that for the above i was checking for exact timestamp matched even after fuzzing 
hence the reduced the correlation 

with the same 48 peers above and the fuzzing ranges 
i started checking for timestamp range instead of the exact timestamps 

1. fuzzed with +/-5 seconds 
checked for +/-10 seconds and i got back the 100% correlation 

2. fuzzed with +/-5 minutes
correlation reduced to +/-10 minutes and i got back the 100% 

3. fuzzed with +/-5 days 
checked for correlation based on +/-10 days and i got back the 100%


why i  choose the check +/-10 is because i realized 
that when i fuzz with +/-5 the biggest difference between two items would be 10 and not 5 so thats the rnage i should use 


actually i found this to be expcted in some ways but i think this will be very different if we applied to all our results 

form the data that we had 

at least one address in common with all timestamps matching	257 (0,05%)
at least one address in common with some (but not all) timestamps matching

now i think that having such a controlled environment using my onw node is not very useful in simulating wether or not this is going to work 
but instead 
my addrman is small 


so i think for this experiment to work
i have to crawl the find the bridges again and then 

and then distort the timestamps by a certain range and then compare the if i am geting the false possitives or not 
the reason why i think the controlled one does not work is because then i dont think we have a specific pair we are comapring against each which doesnt proivide a real attack scenario



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




Hey  i repeated the experiment using my own node.

I matched peers between my IPv4 and Tor connections.

* 48 peers matched.
* Out of those 48 peers, all shared the exact same timestamp.
* My match percentage was 100%.

### Exact timestamp matching after fuzzing

1. Fuzzed with ±5 seconds

   * Correlation reduced to 58%.

2. Fuzzed with ±5 minutes

   * Correlation reduced to 1.8%.

3. Fuzzed with ±5 days

   * Correlation reduced to 0%.

Note that for the results above, I was checking for exact timestamp matches even after fuzzing. Therefore, the correlation dropped significantly.

Using the same 48 peers and the same fuzzing ranges, I then checked for correlation using 2x of the fuzzing range.

1. Fuzzed with ±5 seconds

   * Checked for matches within ±10 seconds.
   * Correlation returned to 100%.

2. Fuzzed with ±5 minutes

   * Checked for matches within ±10 minutes.
   * Correlation returned to 100%.

3. Fuzzed with ±5 days

   * Checked for matches within ±10 days.
   * Correlation returned to 100%.

The reason I chose a matching window of ±10 is that when timestamps are fuzzed by ±5, the maximum possible difference between two corresponding entries is 10, not 5. Therefore, ±10 seemed like the appropriate range to test.

In some ways, I found this result expected. because this is very controlled and the attacker has 1000 of nodes to try and match not just 2 pairs .

I think a more realistic experiment would be to:

1. Crawl and identify the bridges again.
2. Distort timestamps by a chosen range.
3. Re-run the correlation analysis.
4. Measure how many true positives and false positives are produced.

The reason I think the controlled experiment is limited is that we already know we are comparing the same node over IPv4 and Tor. In a real attack scenario, we do not know ahead of time which pairs correspond to the same node, so the key question becomes whether timestamp fuzzing increases ambiguity and false positives enough to make correlation unreliable.


i think a more realistic experiment would be to:
crawl again 
find bridges 
fuzz all the timestamps on my db
and then re run the correlation analysis 
1. first we check the exact timestamp on the correlation analysis 
2. then we check correlation using 2x whatever the range is and then we compare the results 

so we are comparing 3 things 
- we have what our initial bridges are 
- we have the what we get as bridges after we fuzz and check exact timestamps 
- we have what we get after fuzzing and checking 2f the fuzzing range 

that will tell us what to do 


```markdown



so i have been running an experiment to try and break correlation based on timestamps 

this is based on this experiment 
https://delvingbitcoin.org/t/fingerprinting-nodes-via-addr-requests/1786

so i tried this experiment using my own node locally
and the results we as follows 


 i repeated the experiment using my own node.

I matched peers between my IPv4 and Tor connections.

* 48 peers matched.
* Out of those 48 peers, all shared the exact same timestamp.
* My match percentage was 100%.

### Exact timestamp matching after fuzzing

1. Fuzzed with ±5 seconds

   * Correlation reduced to 58%.

2. Fuzzed with ±5 minutes

   * Correlation reduced to 1.8%.

3. Fuzzed with ±5 days

   * Correlation reduced to 0%.

Note that for the results above, I was checking for exact timestamp matches even after fuzzing. Therefore, the correlation dropped significantly.

Using the same 48 peers and the same fuzzing ranges, I then checked for correlation using 2x of the fuzzing range.

1. Fuzzed with ±5 seconds

   * Checked for matches within ±10 seconds.
   * Correlation returned to 100%.

2. Fuzzed with ±5 minutes

   * Checked for matches within ±10 minutes.
   * Correlation returned to 100%.

3. Fuzzed with ±5 days

   * Checked for matches within ±10 days.
   * Correlation returned to 100%.

The reason I chose a matching window of ±10 is that when timestamps are fuzzed by ±5, the maximum possible difference between two corresponding entries is 10, not 5. Therefore, ±10 seemed like the appropriate range to test.

In some ways, I found this result expected. because this is very controlled and the attacker has 1000 of nodes to try and match not just 2 pairs .

I think a more realistic experiment would be to:

1. Crawl and identify the bridges again.
2. Distort timestamps by a chosen range.
3. Re-run the correlation analysis.
4. Measure how many true positives and false positives are produced.

The reason I think the controlled experiment is limited is that we already know we are comparing the same node over IPv4 and Tor. In a real attack scenario, we do not know ahead of time which pairs correspond to the same node, so the key question becomes whether timestamp fuzzing increases ambiguity and false positives enough to make correlation unreliable.


i think a more realistic experiment would be to:
crawl again 
find bridges 
fuzz all the timestamps on my db
and then re run the correlation analysis 
1. first we check the exact timestamp on the correlation analysis 
2. then we check correlation using 2x whatever the range is and then we compare the results 

so we are comparing 3 things 
- we have what our initial bridges are 
- we have the what we get as bridges after we fuzz and check exact timestamps 
- we have what we get after fuzzing and checking 2f the fuzzing range 

that will tell us what to do 

now ideally what i am trying to find is 
what is the perfect rnage to fuzz with to break correlation without and attacker being ableto deffuzz this 


instead of using my own node for this i opted to use all the ipv4 node and tor_nodes that i have crawled in my database and then use the bridges 
in my databses 

i have this tables 

day12_april29_i2p_responses                                 | table | btc_crawler_user
 public | day12_april29_ipv4_responses                      | table | btc_crawler_user
 public | day12_april29_ipv6_responses                      | table | btc_crawler_user
 public | day12_april29_onion_responses 
 public | day12_tor_ipv4_analysis_peer_table                | table | btc_crawler_user
 public | day12_tor_ipv4_analysis_timestamp_table           | table | btc_crawler_user
 public | day12_tor_ipv4_match_ratios


 i have this scripts this folder 

~/Projects/test_exact_matches.py  test_peer_analysis_7.py  test_peer_matching_ratio.py


you can lookat those scripts and the db file to figure out how we are arrigin at the macth ratios and the results 

and then once i have that 
i have to make a decision of what is the best fuzzing range to use 

so i use this script 

/Projects $ code fuzz_correlation_sweep.py

btc_crawler=# select * from day12_fuzz_summary;

and the output is int this table 

i need to underdand each raw table first before underdstanding the results 










this is an explanation for the table above

1. I have two separate tables(not shared here ) in my database from when i crawled the network 
one storing the IPV4 nodes and the other one storing the tor nodes - each together with their peers info

2. from the table above i have the following the first row : is the baseline and i was paring nodes with no fuzzing 

using the tables i mentioned in step 1 i pared the nodes on the tables based on shared peers and then shared timestamps, without fuzzing the timestamps
i measured 3 things 
- Pairs sharing >=1 peer I found 1660 ( tor, ipv4 ) pairs that share at least one address
- Pairs with >=1 exact-timestamp - of those 1660 , 1410 also have at least one shared peer whose timestamp matches exactly 
- Unique tor nodes(possible bridges) - 55 tor nodes have exactly one ipv4 node with which they share the >=5( 5 or more peers ) with the exact matching timestamps 
- another set of tor nodes - tor_n>=5 (2+ suspects) - we have 45 tor nodes that have more than 2 ipv4 nodes which they share >= ( 5 or more peers ) with the exact matching timestamp 


3. Then i introduced fuzzing 

Next form the original table in step 1. i applied fuzzing to all the peers in that based based on a given range ( each range independent)
so for this row i fuzzed within the range of [+/-5] seconds 

and then i ran the correlation analysis again 

note that pairs sharing >= 1 peers this doesn't change, since this is dependant on peers share and not timestamp sharing so it says the same 1,660 

so after fuzzing with a [+/-5] seconds window 
- exact -first i check exact timestamp matches -timestamps that are exactly the same after fuzzing
- +F(wf) - i check timestamps that are withing the fuzzing ranges itself so[+/-5] seconds
- +2f (w2f) - timestamps that are within twice the range so here (+/-10 seconds)

the output for this was 
- 1,660 - pairs sharing at least one peer ( this remains unchanged )
- 1,323 - pairs with at least one share peers whose timestamp fall withing [+/-5] seconds of each other 
- 52 tor nodes with exactly one ipv4 node sharing >=5 peers whose timestamps are within this +/-5 seconds range  
- 23 tor nodes with 2+ ipv4 nodes sharing >=5 peers whose timestamp are within this +/-5 seconds range 



i have this data i a conducting an experiment basically where the 
the first node is a normal node 
and the next one is an experiment node 
one is comparing normal and experiment nodes 

i am at first comparing the terrible and non terrible addresses 

and then 
comparing the addr messages
first i have the messages 
and then i have the addresses 

now i would like to plot three graphs with this updated informations 
graphs like the ones in 
~/Projects/bitcoin-core-notes/p2p/fingeprinting-nodes/node_comparison.png

for the two nodes we are comparing 
terrible vs non-terrible addresses 
messages  getaddr vs gossip
aadress delivered  addresses: getaddr vs  gossip  (getaddr% of delivered addrs)

all this using this data 




June 8th 13:13pm 

normal Node
total=48495 | terrible=58 (0.12%) | non-terrible=48437 (99.88%)
date=2026-06-08 | total_msgs=5650 | getaddr=6 (0.11%) | gossip=5644 (99.89%)

experiment Node
total=66825 | terrible=3571 (5.34%) | non-terrible=63254 (94.66%)
date=2026-06-08 | total_msgs=60 | getaddr=8 (13.33%) | gossip=52 (86.67%)



june 9th 

normal node
total=50956 | terrible=88 (0.17%) | non-terrible=50868 (99.83%)
date=2026-06-09
  messages : getaddr=12  gossip=183
  addresses: getaddr=12000  gossip=522  (getaddr=95.83% of delivered addrs)

9pm
total=54215 | terrible=79 (0.15%) | non-terrible=54136 (99.85%)
date=2026-06-09
  messages : getaddr=22  gossip=5125
  addresses: getaddr=22000  gossip=14878  (getaddr=59.66% of delivered addrs)


experiment node
total=66901 | terrible=2970 (4.44%) | non-terrible=63931 (95.56%)
messages : getaddr=4  gossip=5208
  addresses: getaddr=4000  gossip=13598  (getaddr=22.73% of delivered addrs)


9pm
total=66924 | terrible=2952 (4.41%) | non-terrible=63972 (95.59%)
date=2026-06-09
  messages : getaddr=12  gossip=9391
  addresses: getaddr=12000  gossip=24870  (getaddr=32.55% of delivered addrs)



June11th
normal node
11pm 
total=57954 | terrible=77 (0.13%) | non-terrible=57877 (99.87%)

date=2026-06-11
  messages : getaddr=1  gossip=4942
  addresses: getaddr=1000  gossip=14065  (getaddr=6.64% of delivered addrs)


experiment Node
total=66976 | terrible=2718 (4.06%) | non-terrible=64258 (95.94%)
date=2026-06-11
  messages : getaddr=2  gossip=5005
  addresses: getaddr=2000  gossip=14796  (getaddr=11.91% of delivered addrs)



june 26th

date=2026-06-20
  messages : getaddr=11  gossip=33678
  addresses: getaddr=11000  gossip=102972  (getaddr=9.65% of delivered addrs)

normal node

total=65837 | terrible=333 (0.51%) | non-terrible=65504 (99.49%)

date=2026-06-26
  messages : getaddr=5  gossip=6978
  addresses: getaddr=5000  gossip=18541  (getaddr=21.24% of delivered addrs)


experiment Node

date=2026-06-26
  messages : getaddr=7  gossip=6
  addresses: getaddr=6999  gossip=9  (getaddr=99.87% of delivered addrs)

  total=67380 | terrible=2100 (3.12%) | non-terrible=65280 (96.88%)



July 2nd 

normal node 
total=66402 | terrible=671 (1.01%) | non-terrible=65731 (98.99%)

date=2026-07-02
  messages : getaddr=5  gossip=6561
  addresses: getaddr=5000  gossip=18245  (getaddr=21.51% of delivered addrs)



experiment Node
total=67502 | terrible=1505 (2.23%) | non-terrible=65997 (97.77%)

date=2026-07-02
  messages : getaddr=7  gossip=9829
  addresses: getaddr=7000  gossip=29772  (getaddr=19.04% of delivered addrs)











