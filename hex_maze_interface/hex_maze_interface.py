"""Python interface to the Reiser lab ArenaController."""
import socket
import atexit


class ArenaInterface():
    """Python interface to the Reiser lab ArenaController."""
    PORT = 62222
    def __init__(self, sock=None, debug=True):
        """Initialize a ArenaHost instance."""
        self._debug = debug
        if sock is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
            while totalsent < MSGLEN:
                sent = self._socket.send(msg[totalsent:])
                if sent == 0:
                    raise RuntimeError("socket connection broken")
                totalsent = totalsent + sent

    def connect(self, ip_address):
        """Connect to server at ip address."""
        self._debug_print('ArenaHost connecting...')
        self._socket.connect((ip_address, self.PORT))
        self._debug_print('ArenaHost connected')

    def all_on(self):
        """Turn all panels on."""
        self._send(b'\x01\xff')

    def all_off(self):
        """Turn all panels off."""
        self._send(b'\x01\x00')

