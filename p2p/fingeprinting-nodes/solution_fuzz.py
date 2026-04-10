import random

MAX_OFFSET = 72 * 3600
BUCKET = 6 * 3600

def fuzz(timestamp):
    delta = random.randint(-MAX_OFFSET, MAX_OFFSET)
    t_prime = timestamp + delta
    return round(t_prime / BUCKET) * BUCKET, delta

now = 0
real_timestamp = now - 10 * 86400

addresses = ["xyz.onion", "abc.onion", "1.2.3.4", "5.6.7.8", "def.onion"]

for addr in addresses:
    print(f"addr = {addr}  (real age = 10.00 days)")
    for name in ["IPv4  network", "Tor   network", "I2P   network"]:
        t_final, delta = fuzz(real_timestamp)
        age_final = (now - t_final) / 86400
        delta_h   = delta / 3600
        print(f"  {name}: Δ={delta_h:+.1f}h → {age_final:.2f} days")
    print()






we have a timestamp we want to chnage it value (introduce some noice to it ) so that on every inteface -requestor 
it appears slightly different 
but keep in mind that we old address have to keep being older otherwise updating them to be fresher 
means we will nec=ver have them be terrible 
also we need to eveict this old addresses when theres a bucket collison in addrman 
so when intriducing this noise we need a good slight range not to make them too old or to new form their originla real_timestamp

this is a formular that i believe can help us achieve that
step1: we need a source of controlled randomness h = H(addr, peer, secret)
where different fore each address + peer combination 
but alwaays the same for same combination
this makes it difficltu to reverse this random value 

we hash 3 things to get one big number for example 

H("xyz.onion", "ipv4", "secret") = 84729301847562901
H("xyz.onion", "tor",  "secret") = 31047829104756234
H("abc.onion", "ipv4", "secret") = 59103847291047832

same input -> same output awlays 
diffeerent input -> different output 


step 2: we want a range of how big and small our shift can be [3, 5] days for example
i elected this number rnadomly 
i thought 1 day would be too smale and 7 would be too big


so to get this random range form the range above 
we have use the hash from step 1  h % 2d will walsys give us 0 to 2d - 1

84729301847562901 % 2 = 1   → range = 3 + 1 = 4 days
31047829104756234 % 2 = 0   → range = 3 + 0 = 3 days
59103847291047832 % 2 = 0   → range = 3 + 0 = 3 days

so this will always yield either 3, 4 or 5 days which is excalty what we need

now that we have a range 

step 3: window of time to shift
why is this step important 

if you have a range of 4 days 
and a window of then our window becomes 5 days 

so we need this because step 2 will almost wlasy give you 3, 4 never 5 
and we have this 
[-4d , +1 d]
what this means is we can shift this back by 4 days and only forwrd by 1 day 
why thought why can we shift forwd by 4 day 

does this create the issue of addresses walye being too fresh 
mean the likelyhood of an old adress being updated to be fresher is higher than the likelyhood of it being updated to be older
this is problem becuase of istreebible


step 4: we get the delta of the hahs and the range and the window
Δ = (h % window) - range

at this pint is when we get the actula shify 

h % window

we get a number between 0 and the window 


h = 84729301847562901
window = 5 days = 432000 seconds

h % 432000 = 281901 seconds = 3.26 days

Δ = 3.26 days - 4 days = -0.74 days = -17.8 hours

what this does agin isreduce fuzzing pression but in a determinist way 
of we just choose a random numver between 3 + 5 an attacker could easily defuzz by using this smae window a couple of times 
alo makign it fifficult to recover the actual number 

Start:   real age = 10 days

Step 1:  big hash number from addr+peer+secret
Step 2:  pick shift size between 3 and 5 days     → e.g. 4 days
Step 3:  total window = shift size + 1 day         → 5 days
Step 4:  pick actual shift in [-4d, +1d]           → e.g. -17.8h
Step 5:  apply shift                               → 10.74 days
Step 6:  snap to 6h bucket                         → 10.5 days

IPv4 peer sees: 10.5 days
Tor  peer sees: 13.0 days  (completely different because different peer = different hash)
Real age:       10.0 days  (neither peer can recover this)


why is thi better than fuzzing 

there is no risk of an attacker defuzzing values 

ca this still lead to a zombie 

Δ ∈ [-4d, +1d]

i think the adavtnage of this is that it make the address hop closer to older than making them hop closer to newer
