Deterministic Per-REquestor Distortion 

Each peer sees a consistent but slightly modified timestamps 
same same different with the cache period
different peer a different distorted modified timestamps

B. The next step is quantization (Bucketing)

After we shift the time we round it int chucks or different buckets
so we take a timestamp 
1773923947 
and then next we have something like 
17390000 to the nearest 6 hours of this time 

so a bucketing window of 6 hours would be something like
0h --------> 6hrs -------------> 12hrs --------------------> 18hrs 
if the bucket is 6hours then this becomes 6 hours
all the time between 6 ----------------- 12 hours 
so 
t = floor(t/bucket) * bucket 

so if we have 
10:23 pm then we have 
 6 hour bucket 


Original timestamp
t = 6 days old
Step 1: Apply distortion (Δ)

For IPv4 peer:

Δ = -12 hours
t → 5.5 days

For Tor peer:

Δ = +18 hours
t → 6.75 days