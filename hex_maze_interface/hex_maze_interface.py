"""Python interface to the Reiser lab ArenaController."""
import socket
import nmap3
import struct


PORT = 7777
IP_BASE = '192.168.10.'
IP_RANGE = IP_BASE + '0/24'
REPEAT_LIMIT = 4
PROTOCOL_VERSION = b'\x01'

def results_filter(pair):
    key, value = pair
    try:
        ports = value['ports']
        for port in ports:
            if port['portid'] == str(PORT) and port['state'] == 'open':
                return True
    except (KeyError, TypeError) as e:
        pass

    return False

class HexMazeInterface():
    """Python interface to the Voigts lab hex maze."""
    def __init__(self, debug=True):
        """Initialize a HexMazeInterface instance."""
        self._debug = debug
        self._clusters = None
        self._cluster_address_map = {}
        self._nmap = nmap3.NmapHostDiscovery()
        self._socket = None

    def _debug_print(self, *args):
        """Print if debug is True."""
        if self._debug:
            print(*args)

    def _send_ip_msg_receive_rsp(self, ip_address, msg):
        """Send message to IP address and receive response."""
        repeat_count = 0
        rsp = None
        self._debug_print('msg: ', msg.hex())
        while repeat_count < REPEAT_LIMIT:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                self._debug_print(f'to {ip_address} port {PORT}')
                s.settimeout(2)
                try:
                    s.connect((ip_address, PORT))
                    s.sendall(msg)
                    rsp = s.recv(1024)
                    break
                except (TimeoutError, OSError):
                    self._debug_print('socket timed out')
                    repeat_count += 1
        self._debug_print('rsp: ', rsp.hex())
        return rsp

    def _send_ip_cmd_receive_rsp(self, ip_address, cmd):
        msg = PROTOCOL_VERSION + cmd
        return self._send_ip_msg_receive_rsp(ip_address, msg)

    def _send_cluster_cmd_receive_rsp(self, cluster_address, cmd):
        ip_address = IP_BASE + str(cluster_address)
        return self._send_ip_cmd_receive_rsp(ip_address, cmd)

    def discover_ip_addresses(self):
        results = self._nmap.nmap_portscan_only(IP_RANGE, args=f'-p {PORT}')
        filtered_results = dict(filter(results_filter, results.items()))
        return list(filtered_results.keys())

    def map_cluster_addresses(self):
        ip_addresses = self.discover_ip_addresses()
        self._cluster_address_map = {}
        for ip_address in ip_addresses:
            cluster_address = self.read_cluster_address(ip_address)
            self._cluster_address_map[cluster_address] = ip_address
        return self._cluster_address_map

    def read_cluster_address(self, ip_address):
        cmd = b'\x01'
        rsp = self._send_ip_cmd_receive_rsp(ip_address, cmd)
        return int(rsp[0])

    def check_communication(self, cluster_address):
        """Check communication with cluster."""
        cmd = b'\x02'
        rsp = self._send_cluster_cmd_receive_rsp(cluster_address, cmd)
        return rsp == b'\x12\x34\x56\x78'

    def no_cmd(self, cluster_address):
        """Send no command to get error response."""
        cmd = b''
        rsp = self._send_cluster_cmd_receive_rsp(cluster_address, cmd)
        return rsp == b'\xEE'

    def bad_cmd(self, cluster_address):
        """Send bad command to get error response."""
        cmd = b'\xEE'
        rsp = self._send_cluster_cmd_receive_rsp(cluster_address, cmd)
        return rsp == b'\xEE'

    def reset(self, cluster_address):
        """Reset cluster microcontroller."""
        cmd = b'\x03'
        rsp = self._send_cluster_cmd_receive_rsp(cluster_address, cmd)
        return rsp == cmd

    def beep(self, cluster_address, duration_ms):
        """Command cluster to beep for duration."""
        cmd = struct.pack('<BH', 0x04, duration_ms)
        rsp = self._send_cluster_cmd_receive_rsp(cluster_address, cmd)
        return rsp == cmd

    def power_off(self):
        """Turn all prisms on."""

    def power_on(self):
        """Turn all prisms on."""
