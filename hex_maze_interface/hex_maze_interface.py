"""Python interface to the Reiser lab ArenaController."""
import socket
import atexit
import nmap3

PORT = 7777
IP_RANGE = '192.168.10.0/24'

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
        # if sock is None:
        #     self._socket = socket.socket(socket.AF_INET,
        #                                  socket.SOCK_STREAM)
        # else:
        #     self._socket = sock
        atexit.register(self._exit)

    def _exit(self):
        pass
        # if self._sockets is not None:
        #     for socket in self._sockets:
        #         socket.close()

    def _debug_print(self, to_print):
        """Print if debug is True."""
        if self._debug:
            print(to_print)

    def _send(self, msg):
        """Send message."""
        if self._socket:
            totalsent = 0
            while totalsent < len(msg):
                sent = self._socket.send(msg[totalsent:])
                if sent == 0:
                    raise RuntimeError("socket connection broken")
                totalsent = totalsent + sent

    def discover_cluster_ip_addresses(self):
        results = self._nmap.nmap_portscan_only(IP_RANGE, args=f'-p {PORT}')
        filtered_results = dict(filter(results_filter, results.items()))
        self._cluster_ip_addresses = list(filtered_results.keys())
        return self._cluster_ip_addresses

    def get_cluster_address_map(self):
        if self._cluster_ip_addresses is None:
            self.discover_cluster_ip_addresses()

        self._cluster_address_map = {}
        for cluster_ip_address in self._cluster_ip_addresses:
            _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _socket.connect((cluster_ip_address, PORT))
            _socket.sendall(b'GET_ADDRESSES\n')
            data = _socket.recv(1024)
            decoded_data = data.decode('utf-8')
            split_data = decoded_data.split(' ')
            self._cluster_address_map[int(split_data[0])] = {'ip_address': split_data[1]}
            _socket.close()
        return self._cluster_address_map

    def disconnect(self, ip_address):
        """Shutdown and close socket connect at ip address."""
        self._debug_print('HexMazeInterface disconnecting connecting...')
        self._socket.shutdown()
        self._socket.close()
        self._debug_print('HexMazeInterface connected')

    def send_hello_world(self):
        """Send test message."""
        self._send(b"Hello, World!")

    def send_led_on(self):
        """Send LED_ON message."""
        message = "LED_ON"
        self._socket.sendall(message.encode())

    def say_hello(self):
        print("hello!")

