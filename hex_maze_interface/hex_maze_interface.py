"""Python interface to the Reiser lab ArenaController."""
import socket
import nmap3
import struct
import time


MILLISECONDS_PER_SECOND = 1000

def results_filter(pair):
    key, value = pair
    try:
        ports = value['ports']
        for port in ports:
            if port['portid'] == str(HexMazeInterface.PORT) and port['state'] == 'open':
                return True
    except (KeyError, TypeError) as e:
        pass

    return False

class MazeException(Exception):
    """HexMazeInterface custom exception"""
    pass

class HexMazeInterface():
    PORT = 7777
    IP_BASE = '192.168.10.'
    IP_RANGE = IP_BASE + '0/24'
    REPEAT_LIMIT = 2
    PROTOCOL_VERSION = 0x02
    ERROR_RESPONSE = 0xEE
    ERROR_RESPONSE_LEN = 3
    CHECK_COMMUNICATION_RESPONSE = 0x12345678
    CLUSTER_ADDRESS_MIN = 10
    CLUSTER_ADDRESS_MAX = 17
    PRISM_COUNT = 7
    PROTOCOL_VERSION_INDEX = 0
    LENGTH_INDEX = 1
    COMMAND_NUMBER_INDEX = 2
    FIRST_PARAMETER_INDEX = 3
    LOOP_DELAY_MS = 100

    """Python interface to the Voigts lab hex maze."""
    def __init__(self, debug=False):
        """Initialize a HexMazeInterface instance."""
        self._debug = debug
        self._nmap = nmap3.NmapHostDiscovery()
        self._socket = None
        self._cluster_addresses = []

    def _debug_print(self, *args):
        """Print if debug is True."""
        if self._debug:
            print(*args)

    def _discover_ip_addresses(self):
        results = self._nmap.nmap_portscan_only(HexMazeInterface.IP_RANGE, args=f'-p {HexMazeInterface.PORT}')
        filtered_results = dict(filter(results_filter, results.items()))
        return list(filtered_results.keys())

    def discover_cluster_addresses(self):
        self._cluster_addresses = []
        ip_addresses = self._discover_ip_addresses()
        for ip_address in ip_addresses:
            cluster_address = int(ip_address.split('.')[-1])
            self._cluster_addresses.append(cluster_address)
        return self._cluster_addresses

    def _send_ip_cmd_bytes_receive_rsp_params_bytes(self, ip_address, cmd_bytes):
        """Send command to IP address and receive response."""
        repeat_count = 0
        rsp = None
        self._debug_print('cmd_bytes: ', cmd_bytes.hex())
        while repeat_count < HexMazeInterface.REPEAT_LIMIT:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                self._debug_print(f'to {ip_address} port {HexMazeInterface.PORT}')
                s.settimeout(1)
                try:
                    s.connect((ip_address, HexMazeInterface.PORT))
                    s.sendall(cmd_bytes)
                    rsp_bytes = s.recv(1024)
                    break
                except (TimeoutError, OSError):
                    self._debug_print('socket timed out')
                    repeat_count += 1
        if repeat_count == HexMazeInterface.REPEAT_LIMIT:
            raise MazeException('no response received')
        try:
            self._debug_print('rsp_bytes: ', rsp_bytes.hex())
        except AttributeError:
            pass
        protocol_version = rsp_bytes[HexMazeInterface.PROTOCOL_VERSION_INDEX]
        if protocol_version != HexMazeInterface.PROTOCOL_VERSION:
            raise MazeException(f'response protocol-version is not {HexMazeInterface.PROTOCOL_VERSION}')
        reported_response_length = rsp_bytes[HexMazeInterface.LENGTH_INDEX]
        measured_response_length = len(rsp_bytes)
        if measured_response_length != reported_response_length:
            raise MazeException(f'response length is {measured_response_length} not {reported_response_length}')
        response_command_number = rsp_bytes[HexMazeInterface.COMMAND_NUMBER_INDEX]
        if response_command_number == HexMazeInterface.ERROR_RESPONSE:
            raise MazeException(f'received error response')
        command_command_number = cmd_bytes[HexMazeInterface.COMMAND_NUMBER_INDEX]
        if response_command_number != command_command_number:
            raise MazeException(f'response command-number is {response_command_number} not {command_command_number}')
        return rsp_bytes[HexMazeInterface.FIRST_PARAMETER_INDEX:]

    def _send_cluster_cmd_receive_rsp_params(self, cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par=None, rsp_params_fmt='', rsp_params_len=0):
        if cmd_par is None:
            cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num)
        else:
            try:
                cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num, *cmd_par)
            except TypeError:
                cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num, cmd_par)
        ip_address = HexMazeInterface.IP_BASE + str(cluster_address)
        rsp_params_bytes = self._send_ip_cmd_bytes_receive_rsp_params_bytes(ip_address, cmd_bytes)
        if len(rsp_params_bytes) != rsp_params_len:
            raise MazeException(f'response parameter length is {len(rsp_params_bytes)} not {rsp_params_len}')
        rsp_params = struct.unpack(rsp_params_fmt, rsp_params_bytes)
        if len(rsp_params) == 1:
            return rsp_params[0]
        return rsp_params

    def no_cmd(self, cluster_address):
        """Send no command to get error response."""
        cmd_fmt = '<BB'
        cmd_len = 2
        cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len)
        ip_address = HexMazeInterface.IP_BASE + str(cluster_address)
        self._send_ip_cmd_bytes_receive_rsp_params_bytes(ip_address, cmd_bytes)

    def bad_cmd(self, cluster_address):
        """Send bad command to get error response."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = HexMazeInterface.ERROR_RESPONSE
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def read_cluster_address(self, ip_address):
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x01
        cmd_par = None
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num)
        rsp_params_bytes = self._send_ip_cmd_bytes_receive_rsp_params_bytes(ip_address, cmd_bytes)
        print(rsp_params_bytes)
        rsp_params = struct.unpack(rsp_params_fmt, rsp_params_bytes)
        cluster_address = rsp_params[0]
        return cluster_address

    def check(self, cluster_address):
        """Check communication with cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x02
        cmd_par = None
        rsp_params_fmt = '<L'
        rsp_params_len = 4
        communication_response = self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
        return communication_response == HexMazeInterface.CHECK_COMMUNICATION_RESPONSE

    def check_all(self):
        """Check communication with all clusters."""
        communicating = []
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                c = self.check(cluster_address)
            except MazeException:
                c = False
            communicating.append(c)
            time.sleep(HexMazeInterface.LOOP_DELAY_MS/MILLISECONDS_PER_SECOND)
        return communicating

    def reset(self, cluster_address):
        """Reset cluster microcontroller."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x03
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def beep(self, cluster_address, duration_ms):
        """Command cluster to beep for duration."""
        cmd_fmt = '<BBBH'
        cmd_len = 5
        cmd_num = 0x04
        cmd_par = duration_ms
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)

    def beep_all(self, duration_ms):
        """Command all clusters to beep for duration."""
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                self.beep(cluster_address, duration_ms)
                time.sleep(duration_ms/MILLISECONDS_PER_SECOND)
            except MazeException:
                pass

    def measure_communication(self, cluster_address, repeat_count):
        time_begin = time.time()
        for i in range(repeat_count):
            self.led_on_then_off(cluster_address)
        time_end = time.time()
        # led-on-then-off is 2 commands so multiply repeat_count by 2
        duration = (time_end - time_begin) / (repeat_count * 2)
        self._debug_print("duration = ", duration)
        return duration

    def led_on_then_off(self, cluster_address):
        self.led_on(cluster_address)
        self.led_off(cluster_address)

    def led_off(self, cluster_address):
        """Turn cluster pcb LED off."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x05
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def led_on(self, cluster_address):
        """Turn cluster pcb LED on."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x06
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def power_off(self, cluster_address):
        """Turn off power to all prisms in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x07
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def power_off_all(self):
        """Turn off power to all clusters prisms."""
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                self.power_off(cluster_address)
            except MazeException:
                pass
            time.sleep(HexMazeInterface.LOOP_DELAY_MS/MILLISECONDS_PER_SECOND)

    def power_on(self, cluster_address):
        """Turn on power to all cluster prisms."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x08
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def power_on_all(self):
        """Turn on power to all clusters prisms."""
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                self.power_on(cluster_address)
            except MazeException:
                pass
            time.sleep(HexMazeInterface.LOOP_DELAY_MS/MILLISECONDS_PER_SECOND)

    def home(self, cluster_address):
        """Home all prisms in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x0A
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def home_all(self):
        """Home all prisms in all clusters."""
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                self.home(cluster_address)
            except MazeException:
                pass
            time.sleep(HexMazeInterface.LOOP_DELAY_MS/MILLISECONDS_PER_SECOND)

    def write_target_positions(self, cluster_address, positions_mm):
        """Write target positions to all prisms in a single cluster."""
        cmd_fmt = '<BBBHHHHHHH'
        cmd_len = 17
        cmd_num = 0x0C
        cmd_par = positions_mm
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)

    def pause(self, cluster_address):
        """Pause all prisms in a cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x0E
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def pause_all(self):
        """Pause all prisms in all clusters."""
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                self.pause(cluster_address)
            except MazeException:
                pass
            time.sleep(HexMazeInterface.LOOP_DELAY_MS/MILLISECONDS_PER_SECOND)

    def resume(self, cluster_address):
        """Resume all prisms in a cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x10
        self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)

    def resume_all(self):
        """Resume all prisms in all clusters."""
        for cluster_address in range(HexMazeInterface.CLUSTER_ADDRESS_MIN, HexMazeInterface.CLUSTER_ADDRESS_MAX):
            try:
                self.resume(cluster_address)
            except MazeException:
                pass
            time.sleep(HexMazeInterface.LOOP_DELAY_MS/MILLISECONDS_PER_SECOND)

    def read_actual_positions(self, cluster_address):
        """Read actual position from every prism in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x11
        cmd_par = None
        rsp_params_fmt = '<hhhhhhh'
        rsp_params_len = 14
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)

