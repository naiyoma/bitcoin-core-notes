#!/usr/bin/env python3
import time
import socket
from test_framework.p2p import P2PInterface, msg_getaddr
from commander import Commander

class AddrReceiver(P2PInterface):
    def __init__(self):
        super().__init__()
        self.received_addrs = None

    def on_addr(self, message):
        self.received_addrs = [addr.ip for addr in message.addrs]

    def on_addrv2(self, message):
        self.received_addrs = [addr.ip for addr in message.addrs]

    def addr_received(self):
        return self.received_addrs is not None

class GetAddrScenario(Commander):
    def set_test_params(self):
        self.num_nodes = 1

    def run_test(self):
        node = self.tanks["tank-0000"]

        # 1. FILL ADDRMAN (Using diverse IPs to hit 2000+)
        self.log.info("Step 1: Filling AddrMan with diverse records...")
        for i in range(2500):
            # Creates diverse net groups: x.y.1.1
            ip = f"{(i % 254) + 1}.{(i >> 8) % 254 + 1}.1.1"
            node.addpeeraddress(ip, 8333)
        total_addr = len(node.getnodeaddresses(0))
        self.log.info(f"AddrMan has {total_addr} addresses.") 
        # 2. MANUAL P2P CONNECTION
        dstaddr = socket.gethostbyname(node.rpchost)
        dstport = 18444
        self.log.info(f"Step 2: Connecting P2P Interface to {dstaddr}:{dstport}")
        attacker = AddrReceiver()
        # Pass the timeout_factor from the Commander options
        attacker.peer_connect(
            dstaddr=dstaddr, 
            dstport=dstport, 
            net="regtest", 
            timeout_factor=self.options.timeout_factor
        )()
        # Check connection status
        attacker.wait_until(lambda: attacker.is_connected, check_connected=False)
        self.log.info("P2P Connection Established.")

        # 3. AGE CONNECTION & TRIGGER
        cur_time = int(time.time())
        node.setmocktime(cur_time)
        
        # Advance time to mature the peer
        cur_time += 500
        node.setmocktime(cur_time)
        attacker.sync_with_ping()

        self.log.info("Step 3: Sending getaddr and pumping the relay...")
        attacker.send_message(msg_getaddr())

        # 4. PUMP RELAY (Poisson trigger)
        for i in range(10):
            cur_time += 300 # 5-minute jumps
            node.setmocktime(cur_time)
            attacker.sync_with_ping()
            
            if attacker.addr_received():
                self.log.info(f"Success! Received {len(attacker.received_addrs)} addresses.")
                break
            time.sleep(0.5)

        # 5. FINAL VERIFICATION
        attacker.wait_until(lambda: attacker.addr_received(), timeout=15)
        self.log.info(f"First 5 addresses: {attacker.received_addrs[:5]}")

def main():
    GetAddrScenario().main()

if __name__ == "__main__":
    main()