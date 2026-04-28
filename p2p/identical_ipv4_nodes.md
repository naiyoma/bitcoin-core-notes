Small getaddr responses from 897 nodes

I ran this crawler(https://github.com/virtu/p2p-crawler.git)  over the weekend and observed a cluster of 897 nodes that returned a getaddr response of 256 peers. This is way below the usual  < 990.



All the nodes have the same user_agent, service, and version.


I attempted to cluster these 897 nodes based on shared peers.

Across all of them, the union is 2,006 distinct peers; none is unique to any single node in the group. 

Every pair of cluster nodes shares between 16 and 60 peers, with most pairs at 31-35. No pair shares 100%. 

I had initially thought these peers might be part of this -> https://bnoc.xyz/t/python-bitcoinlib-0-12-2-client-getting-addr-ratelimited-since-2026-04-10/116
But most cluster nodes are hosted on Linode (Akamai Connected Cloud, AS63949), per ipinfo.io lookups.I think its a completely set of addresses 





