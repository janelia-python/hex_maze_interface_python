"""Python interface to the Reiser lab ArenaController."""
import socket
import nmap3
import struct


PORT = 7777
IP_BASE = '192.168.10.'
IP_RANGE = IP_BASE + '0/24'
REPEAT_LIMIT = 4
PROTOCOL_VERSION = 0x01
ERROR_RESPONSE = 0xEE
CHECK_COMMUNICATION_RESPONSE = 0x12345678
CLUSTER_ADDRESS_MIN = 10
CLUSTER_ADDRESS_MAX = 255

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
        self._nmap = nmap3.NmapHostDiscovery()
        self._socket = None
        self._cluster_addresses = []

    def _debug_print(self, *args):
        """Print if debug is True."""
        if self._debug:
            print(*args)

    def _send_ip_cmd_receive_rsp(self, ip_address, cmd):
        """Send command to IP address and receive response."""
        repeat_count = 0
        rsp = None
        self._debug_print('cmd: ', cmd.hex())
        while repeat_count < REPEAT_LIMIT:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                self._debug_print(f'to {ip_address} port {PORT}')
                s.settimeout(2)
                try:
                    s.connect((ip_address, PORT))
                    s.sendall(cmd)
                    rsp = s.recv(1024)
                    break
                except (TimeoutError, OSError):
                    self._debug_print('socket timed out')
                    repeat_count += 1
        try:
            self._debug_print('rsp: ', rsp.hex())
        except AttributeError:
            pass
        return rsp

    def _send_cluster_cmd_receive_rsp(self, cluster_address, cmd):
        ip_address = IP_BASE + str(cluster_address)
        return self._send_ip_cmd_receive_rsp(ip_address, cmd)

    def _discover_ip_addresses(self):
        results = self._nmap.nmap_portscan_only(IP_RANGE, args=f'-p {PORT}')
        filtered_results = dict(filter(results_filter, results.items()))
        return list(filtered_results.keys())

    def discover_cluster_addresses(self):
        self._cluster_addresses = []
        ip_addresses = self._discover_ip_addresses()
        for ip_address in ip_addresses:
            cluster_address = int(ip_address.split('.')[-1])
            self._cluster_addresses.append(cluster_address)
        return self._cluster_addresses

    def read_cluster_address(self, ip_address):
        cmd_num = 0x01
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_ip_cmd_receive_rsp(ip_address, cmd))[0]
        return rsp

    def check_communication(self, cluster_address):
        """Check communication with cluster."""
        cmd_num = 0x02
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<L', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == CHECK_COMMUNICATION_RESPONSE

    def no_cmd(self, cluster_address):
        """Send no command to get error response."""
        cmd = struct.pack('<B', PROTOCOL_VERSION)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == ERROR_RESPONSE

    def bad_cmd(self, cluster_address):
        """Send bad command to get error response."""
        cmd_num = ERROR_RESPONSE
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == ERROR_RESPONSE

    def reset(self, cluster_address):
        """Reset cluster microcontroller."""
        cmd_num = 0x03
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == cmd_num

    def beep(self, cluster_address, duration_ms):
        """Command cluster to beep for duration."""
        cmd_num = 0x04
        cmd = struct.pack('<BBH', PROTOCOL_VERSION, cmd_num, duration_ms)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == cmd_num

    def led_off(self, cluster_address):
        """Turn cluster pcb LED off."""
        cmd_num = 0x05
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == cmd_num

    def led_on(self, cluster_address):
        """Turn cluster pcb LED on."""
        cmd_num = 0x06
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == cmd_num

    def power_off(self, cluster_address):
        """Turn off power to all cluster prisms."""
        cmd_num = 0x07
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == cmd_num

    def power_on(self, cluster_address):
        """Turn on power to all cluster prisms."""
        cmd_num = 0x08
        cmd = struct.pack('<BB', PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
        return rsp == cmd_num
