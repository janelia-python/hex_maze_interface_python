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

class HomeParameters:
    def __init__(self,
                 travel_limit=500,
                 max_velocity=20,
                 run_current=50,
                 stall_threshold=10):
        self.travel_limit = travel_limit
        self.max_velocity = max_velocity
        self.run_current = run_current
        self.stall_threshold = stall_threshold

    def __str__(self):
        s = ''
        for key, value in vars(self).items():
            s += f'{key} = {value}\n'
        return s

class ControllerParameters:
    def __init__(self,
                 start_velocity=1,
                 stop_velocity=5,
                 first_velocity=10,
                 max_velocity=20,
                 first_acceleration=40,
                 max_acceleration=20,
                 max_deceleration=30,
                 first_deceleration=50):
        self.start_velocity = start_velocity
        self.stop_velocity = stop_velocity
        self.first_velocity = first_velocity
        self.max_velocity = max_velocity
        self.first_acceleration = first_acceleration
        self.max_acceleration = max_acceleration
        self.max_deceleration = max_deceleration
        self.first_deceleration = first_deceleration

    def __str__(self):
        s = ''
        for key, value in vars(self).items():
            s += f'{key} = {value}\n'
        return s

class HexMazeInterface():
    PORT = 7777
    IP_BASE = '192.168.10.'
    IP_RANGE = IP_BASE + '0/24'
    REPEAT_LIMIT = 2
    PROTOCOL_VERSION = 0x04
    ERROR_RESPONSE = 0xEE
    ERROR_RESPONSE_LEN = 3
    CHECK_COMMUNICATION_RESPONSE = 0x12345678
    CLUSTER_ADDRESS_MIN = 10
    CLUSTER_ADDRESS_MAX = 17
    CLUSTER_ADDRESSES = range(CLUSTER_ADDRESS_MIN, CLUSTER_ADDRESS_MAX)
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

    def communicating_cluster(self, cluster_address):
        """Check communication with cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x02
        cmd_par = None
        rsp_params_fmt = '<L'
        rsp_params_len = 4
        try:
            communication_response = self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
            return communication_response == HexMazeInterface.CHECK_COMMUNICATION_RESPONSE
        except MazeException:
            return False

    def communicating_all_clusters(self):
        """Check communication with all clusters."""
        return list(map(self.communicating_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def reset_cluster(self, cluster_address):
        """Reset cluster microcontroller."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x03
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def reset_all_clusters(self):
        """Reset all cluster microcontrollers."""
        return list(map(self.reset_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def beep_cluster(self, cluster_address, duration_ms):
        """Command cluster to beep for duration."""
        cmd_fmt = '<BBBH'
        cmd_len = 5
        cmd_num = 0x04
        cmd_par = duration_ms
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)
            time.sleep(duration_ms/MILLISECONDS_PER_SECOND)
            return True
        except MazeException:
            return False

    def beep_all_clusters(self, duration_ms):
        """Command all clusters to beep for duration."""
        duration_ms_list = [duration_ms] * HexMazeInterface.PRISM_COUNT
        return list(map(self.beep_cluster, HexMazeInterface.CLUSTER_ADDRESSES, duration_ms_list))

    def led_off_cluster(self, cluster_address):
        """Turn cluster pcb LED off."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x05
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def led_off_all_clusters(self):
        """Turn all cluster pcb LEDs off."""
        return list(map(self.led_off_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def led_on_cluster(self, cluster_address):
        """Turn cluster pcb LED on."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x06
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def led_on_all_clusters(self):
        """Turn all cluster pcb LEDs on."""
        return list(map(self.led_on_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def measure_communication_cluster(self, cluster_address, repeat_count):
        time_begin = time.time()
        for i in range(repeat_count):
            self.led_on_then_off_cluster(cluster_address)
        time_end = time.time()
        # led-on-then-off is 2 commands so multiply repeat_count by 2
        duration = (time_end - time_begin) / (repeat_count * 2)
        self._debug_print("duration = ", duration)
        return duration

    def led_on_then_off_cluster(self, cluster_address):
        self.led_on_cluster(cluster_address)
        self.led_off_cluster(cluster_address)

    def power_off_cluster(self, cluster_address):
        """Turn off power to all prisms in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x07
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def power_off_all_clusters(self):
        """Turn off power to all clusters prisms."""
        return list(map(self.power_off_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def power_on_cluster(self, cluster_address):
        """Turn on power to all cluster prisms."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x08
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def power_on_all_clusters(self):
        """Turn on power to all clusters prisms."""
        return list(map(self.power_on_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def home_prism(self, cluster_address, prism_address, home_parameters):
        """Home single prism in a single cluster."""
        cmd_fmt = '<BBBBHBBb'
        cmd_len = 9
        cmd_num = 0x09
        cmd_par = (prism_address,
                   home_parameters.travel_limit,
                   home_parameters.max_velocity,
                   home_parameters.run_current,
                   home_parameters.stall_threshold)
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
            return True
        except MazeException:
            return False

    def home_cluster(self, cluster_address, home_parameters):
        """Home all prisms in a single cluster."""
        cmd_fmt = '<BBBHBBb'
        cmd_len = 8
        cmd_num = 0x0A
        cmd_par = (home_parameters.travel_limit,
                   home_parameters.max_velocity,
                   home_parameters.run_current,
                   home_parameters.stall_threshold)
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)
            return True
        except MazeException:
            return False

    def home_all_clusters(self, home_parameters):
        """Home all prisms in all clusters."""
        home_parameters_list = [home_parameters] * HexMazeInterface.PRISM_COUNT
        return list(map(self.home_cluster, HexMazeInterface.CLUSTER_ADDRESSES, home_parameters_list))

    def homed_cluster(self, cluster_address):
        """Read homed value from every prism in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x0B
        cmd_par = None
        rsp_params_fmt = '<BBBBBBB'
        rsp_params_len = 7
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)

    def write_target_prism(self, cluster_address, prism_address, position_mm):
        """Write target position to a single prism in a single cluster."""
        cmd_fmt = '<BBBBH'
        cmd_len = 6
        cmd_num = 0x0C
        cmd_par = (prism_address, position_mm)
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
            return True
        except MazeException:
            return False

    def write_targets_cluster(self, cluster_address, positions_mm):
        """Write target positions to all prisms in a single cluster."""
        cmd_fmt = '<BBBHHHHHHH'
        cmd_len = 17
        cmd_num = 0x0D
        cmd_par = positions_mm
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)
            return True
        except MazeException:
            return False

    def pause_prism(self, cluster_address, prism_address):
        """Pause single prism in a single cluster."""
        cmd_fmt = '<BBBB'
        cmd_len = 4
        cmd_num = 0x0E
        cmd_par = prism_address
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
            return True
        except MazeException:
            return False

    def pause_cluster(self, cluster_address):
        """Pause all prisms in a cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x0F
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def pause_all_clusters(self):
        """Pause all prisms in all clusters."""
        return list(map(self.pause_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def resume_prism(self, cluster_address, prism_address):
        """Resume single prism in a single cluster."""
        cmd_fmt = '<BBBB'
        cmd_len = 4
        cmd_num = 0x10
        cmd_par = prism_address
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
            return True
        except MazeException:
            return False

    def resume_cluster(self, cluster_address):
        """Resume all prisms in a cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x11
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num)
            return True
        except MazeException:
            return False

    def resume_all_clusters(self):
        """Resume all prisms in all clusters."""
        return list(map(self.resume_cluster, HexMazeInterface.CLUSTER_ADDRESSES))

    def read_positions_cluster(self, cluster_address):
        """Read actual position from every prism in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x12
        cmd_par = None
        rsp_params_fmt = '<hhhhhhh'
        rsp_params_len = 14
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)

    def write_run_current_cluster(self, cluster_address, current_percent):
        """Write run current to all prisms in a single cluster."""
        cmd_fmt = '<BBBB'
        cmd_len = 4
        cmd_num = 0x13
        cmd_par = current_percent
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)
            return True
        except MazeException:
            return False

    def read_run_current_cluster(self, cluster_address):
        """Read run current for all prisms in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x14
        cmd_par = None
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)

    def write_run_current_all_clusters(self, current_percent):
        """Write run current to all prisms in all clusters."""
        current_percent_list = [current_percent] * HexMazeInterface.PRISM_COUNT
        return list(map(self.write_run_current_cluster, HexMazeInterface.CLUSTER_ADDRESSES, current_percent_list))

    def write_controller_parameters_cluster(self, cluster_address, controller_parameters):
        """Write controller parameters to all prisms in a single cluster."""
        cmd_fmt = '<BBBBBBBBBBB'
        cmd_len = 11
        cmd_num = 0x15
        cmd_par = (controller_parameters.start_velocity,
                   controller_parameters.stop_velocity,
                   controller_parameters.first_velocity,
                   controller_parameters.max_velocity,
                   controller_parameters.first_acceleration,
                   controller_parameters.max_acceleration,
                   controller_parameters.max_deceleration,
                   controller_parameters.first_deceleration)
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)
            return True
        except MazeException:
            return False

    def read_controller_parameters_cluster(self, cluster_address):
        """Read controller parameters for all prisms in a single cluster."""
        cmd_fmt = '<BBB'
        cmd_len = 3
        cmd_num = 0x16
        cmd_par = None
        rsp_params_fmt = '<BBBBBBBB'
        rsp_params_len = 8
        controller_parameters_tuple = self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
        return ControllerParameters(*controller_parameters_tuple)

    def write_controller_parameters_all_clusters(self, controller_parameters):
        """Write controller parameters to all prisms in all clusters."""
        controller_parameters_list = [controller_parameters] * HexMazeInterface.PRISM_COUNT
        return list(map(self.write_controller_parameters_cluster, HexMazeInterface.CLUSTER_ADDRESSES, controller_parameters_list))

    def write_double_target_prism(self, cluster_address, prism_address, double_position_mm):
        """Write two target positions to a single prism in a single cluster."""
        cmd_fmt = '<BBBBHH'
        cmd_len = 8
        cmd_num = 0x17
        cmd_par = (prism_address, *double_position_mm)
        rsp_params_fmt = '<B'
        rsp_params_len = 1
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par, rsp_params_fmt, rsp_params_len)
            return True
        except MazeException:
            return False

    def write_double_targets_cluster(self, cluster_address, double_positions_mm):
        """Write two target positions to all prisms in a single cluster."""
        cmd_fmt = '<BBBHHHHHHHHHHHHHH'
        cmd_len = 31
        cmd_num = 0x18
        cmd_par = sum(double_positions_mm, ()) # flatten 2D tuple
        try:
            self._send_cluster_cmd_receive_rsp_params(cluster_address, cmd_fmt, cmd_len, cmd_num, cmd_par)
            return True
        except MazeException:
            return False

