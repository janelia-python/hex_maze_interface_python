"""Python interface to the Reiser lab ArenaController."""
import socket
import atexit


class HexMazeInterface():
    """Python interface to the Voigts lab hex maze."""
    IP_ADDRESS = "192.168.10.216"
    PORT = 7777
    def __init__(self, sock=None, debug=True):
        """Initialize a HexMazeInterface instance."""
        self._debug = debug
        if sock is None:
            self._socket = socket.socket(socket.AF_INET,
                                         socket.SOCK_STREAM)
        else:
            self._socket = sock
        atexit.register(self._exit)

    def _exit(self):
        self._socket.close()

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

    def connect(self):
        """Connect to server at ip address."""
        self._debug_print('HexMazeInterface connecting...')
        self._socket.connect((self.IP_ADDRESS, self.PORT))
        self._debug_print('HexMazeInterface connected')

    def send_hello_world(self):
        """Send test message."""
        self._send(b"Hello, World!")

