"""Python interface to the Reiser lab ArenaController."""
import socket
import nmap3
import struct
import time


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
    REPEAT_LIMIT = 4
    PROTOCOL_VERSION = 0x02
    ERROR_RESPONSE = 0xEE
    ERROR_RESPONSE_LEN = 3
    CHECK_COMMUNICATION_RESPONSE = 0x12345678
    CLUSTER_ADDRESS_MIN = 10
    CLUSTER_ADDRESS_MAX = 255
    PRISM_COUNT = 7
    PROTOCOL_VERSION_INDEX = 0
    LENGTH_INDEX = 1
    COMMAND_NUMBER_INDEX = 2
    FIRST_PARAMETER_INDEX = 3

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
                s.settimeout(2)
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
        command_command_number = cmd_bytes[HexMazeInterface.COMMAND_NUMBER_INDEX]
        response_command_number = rsp_bytes[HexMazeInterface.COMMAND_NUMBER_INDEX]
        if response_command_number == HexMazeInterface.ERROR_RESPONSE:
            raise MazeException(f'received error response')
        if response_command_number != response_command_number:
            raise MazeException(f'response command-number is {response_command_number} not {command_command_number}')
        return rsp_bytes[HexMazeInterface.FIRST_PARAMETER_INDEX:]

    def _send_cluster_cmd_receive_rsp_params(self, cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len):
        if cmd_par is None:
            cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num)
        else:
            cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num, *cmd_par)
        ip_address = HexMazeInterface.IP_BASE + str(cluster_address)
        rsp_params_bytes = self._send_ip_cmd_bytes_receive_rsp_params_bytes(ip_address, cmd_bytes)
        if len(rsp_params_bytes) != rsp_params_len:
            raise MazeException(f'response parameter length is {len(rsp_params_bytes)} not {rsp_params_len}')
        return struct.unpack(rsp_params_fmt, rsp_params_bytes)

    # def no_cmd(self, cluster_address):
    #     """Send no command to get error response."""
    #     cmd = struct.pack('<B', HexMazeInterface.PROTOCOL_VERSION)
    #     rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
    #     return rsp == HexMazeInterface.ERROR_RESPONSE

    # def bad_cmd(self, cluster_address):
    #     """Send bad command to get error response."""
    #     cmd_num = HexMazeInterface.ERROR_RESPONSE
    #     cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
    #     rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp(cluster_address, cmd))[0]
    #     return rsp == HexMazeInterface.ERROR_RESPONSE

    def read_cluster_address(self, ip_address):
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x01
        cmd_par = None
        rsp_fmt = '<BBBB'
        rsp_len = 4
        cmd_bytes = struct.pack(cmd_fmt, HexMazeInterface.PROTOCOL_VERSION, cmd_len, cmd_num)
        rsp_bytes = self._send_ip_cmd_bytes_receive_rsp_params_bytes(ip_address, cmd_bytes)
        rsp = struct.unpack(rsp_fmt, rsp_bytes)
        cluster_address = rsp[HexMazeInterface.FIRST_RESPONSE_PARAMETER_INDEX]
        return cluster_address

    def check_communication(self, cluster_address):
        """Check communication with cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x02
        cmd_par = None
        rsp_params_fmt = '<L'
        rsp_params_len = 4
        communication_response = self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
        return communication_response[0] == HexMazeInterface.CHECK_COMMUNICATION_RESPONSE

    def reset(self, cluster_address):
        """Reset cluster microcontroller."""
        cmd_num = 0x03
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def beep(self, cluster_address, duration_ms):
        """Command cluster to beep for duration."""
        cmd_num = 0x04
        cmd = struct.pack('<BBH', HexMazeInterface.PROTOCOL_VERSION, cmd_num, duration_ms)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

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
        cmd_num = 0x05
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def led_on(self, cluster_address):
        """Turn cluster pcb LED on."""
        cmd_num = 0x06
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def power_off_all(self, cluster_address):
        """Turn off power to all cluster prisms."""
        cmd_num = 0x07
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def power_on_all(self, cluster_address):
        """Turn on power to all cluster prisms."""
        cmd_num = 0x08
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def home(self, cluster_address, prism_address):
        """Home a single prism in a cluster."""
        cmd_num = 0x09
        cmd = struct.pack('<BBB', HexMazeInterface.PROTOCOL_VERSION, cmd_num, prism_address)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def home_all(self, cluster_address):
        """Home all prisms in a cluster."""
        cmd_num = 0x0A
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def write_target_position(self, cluster_address, prism_address, position_mm):
        """Write target position to a single prism in a cluster."""
        cmd_num = 0x0B
        cmd = struct.pack('<BBBH', HexMazeInterface.PROTOCOL_VERSION, cmd_num, prism_address, position_mm)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def write_all_target_positions(self, cluster_address, positions_mm):
        """Write target positions to all prisms in a cluster."""
        cmd_num = 0x0C
        cmd = struct.pack('<BBHHHHHHH', HexMazeInterface.PROTOCOL_VERSION, cmd_num, *positions_mm)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def pause(self, cluster_address, prism_address):
        """Pause a single prism in a cluster."""
        cmd_num = 0x0D
        cmd = struct.pack('<BBB', HexMazeInterface.PROTOCOL_VERSION, cmd_num, prism_address)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def pause_all(self, cluster_address):
        """Pause all prisms in a cluster."""
        cmd_num = 0x0E
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def resume(self, cluster_address, prism_address):
        """Resume a single prism in a cluster."""
        cmd_num = 0x0F
        cmd = struct.pack('<BBB', HexMazeInterface.PROTOCOL_VERSION, cmd_num, prism_address)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

    def resume_all(self, cluster_address):
        """Resume all prisms in a cluster."""
        cmd_num = 0x10
        cmd = struct.pack('<BB', HexMazeInterface.PROTOCOL_VERSION, cmd_num)
        rsp = struct.unpack('<B', self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd))[0]
        return rsp == cmd_num

