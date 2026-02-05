#!/usr/bin/env python3
"""Debug addr response - wait in real time"""

import time
from test_framework.p2p import P2PInterface, p2p_lock
from commander import Commander

from test_framework.messages import msg_getaddr, msg_verack


class AddrReceiver(P2PInterface):
    def __init__(self, send_getaddr=True):
        super().__init__()
        self.num_ipv4_received = 0
        self.send_getaddr = send_getaddr

    def on_version(self, message):
        self.send_version()
        self.send_without_ping(msg_verack())
        if self.send_getaddr:
            self.send_without_ping(msg_getaddr())

    def on_addr(self, message):
        for addr in message.addrs:
            self.num_ipv4_received += 1

    def on_addrv2(self, message):
        for addr in message.addrs:
            self.num_ipv4_received += 1

    def addr_received(self):
        return self.num_ipv4_received > 0


class AddrTest(Commander):
    def set_test_params(self):
        self.num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        self.extra_args = [["-whitelist=addr@10.244.0.0/16"]]
        

        # 1. Fill AddrMan
        self.log.info('Filling AddrMan...')
        for i in range(10000):
            first_octet = i >> 8
            second_octet = i % 256
            a = f"{first_octet}.{second_octet}.1.1"
            node.addpeeraddress(a, 8333)

        # 2. Set initial mocktime BEFORE connecting
        self.mocktime = int(time.time())
        node.setmocktime(self.mocktime)

        # 3. Connect
        self.log.info(f'Connecting to {node.rpchost}:18444')
        addr_receiver = node.add_p2p_connection(
            AddrReceiver(),
            dstaddr=str(node.rpchost),
            dstport=18444
        )
        addr_receiver.sync_with_ping()
        self.log.info('Connected!')

        # 4. Jump mocktime to trigger addr send
        self.mocktime += 10 * 60
        node.setmocktime(self.mocktime)

        # 5. Wait for response
        self.log.info('Waiting for addr response...')
        addr_receiver.wait_until(addr_receiver.addr_received, timeout=60)
        self.log.info(f'Got {addr_receiver.num_ipv4_received} addresses')


def main():
    AddrTest(__file__).main()


if __name__ == "__main__":
    main()