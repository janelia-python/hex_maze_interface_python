"""Python interface to the Reiser lab ArenaController."""
import socket
import nmap3


PORT = 7777
IP_RANGE = '192.168.10.0/24'
REPEAT_LIMIT = 4

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
        self._cluster_ip_addresses = None
        self._nmap = nmap3.NmapHostDiscovery()
        self._socket = None

    def _debug_print(self, *args):
        """Print if debug is True."""
        if self._debug:
            print(*args)

    def _send_and_receive(self, msg):
        """Send message and receive response."""
        repeat_count = 0
        while repeat_count < REPEAT_LIMIT:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                self._debug_print(f'to {IP_ADDRESS} port {PORT}')
                s.settimeout(2)
                try:
                    s.connect((IP_ADDRESS, PORT))
                    s.sendall(msg)
                    response = s.recv(1024)
                    break
                except (TimeoutError, OSError):
                    self._debug_print('socket timed out')
                    response = None
                    repeat_count += 1
        self._debug_print('response: ', response)

    def reset(self):
        """Reset cluster microcontroller."""
        self._send_and_receive(b'\x01')

    def power_off(self):
        """Turn all prisms on."""
        self._send_and_receive(b'\x02')

    def all_on(self):
        """Turn all prisms on."""
        self._send_and_receive(b'\x03')

    def discover_cluster_ip_addresses(self):
        results = self._nmap.nmap_portscan_only(IP_RANGE, args=f'-p {PORT}')
        filtered_results = dict(filter(results_filter, results.items()))
        self._cluster_ip_addresses = list(filtered_results.keys())
        return self._cluster_ip_addresses

    def get_cluster_address_map(self):
        if self._cluster_ip_addresses is None:
            self.discover_cluster_ip_addresses()

        self._cluster_address_map = {}
        # for cluster_ip_address in self._cluster_ip_addresses:
        #     _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #     _socket.connect((cluster_ip_address, PORT))
        #     _socket.sendall(b'GET_ADDRESSES\n')
        #     data = _socket.recv(1024)
        #     decoded_data = data.decode('utf-8')
        #     split_data = decoded_data.split(' ')
        #     self._cluster_address_map[int(split_data[0])] = {'ip_address': split_data[1]}
        #     _socket.close()
        return self._cluster_address_map
