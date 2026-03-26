"""Python interface to the Voigts lab hex maze."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import socket
import struct
import time
from typing import Any

try:
    import nmap3
except ModuleNotFoundError:  # pragma: no cover - exercised when discovery is unavailable
    nmap3 = None


MILLISECONDS_PER_SECOND = 1000
SOCKET_TIMEOUT_S = 1.0


class MazeException(Exception):
    """Base exception for HexMazeInterface failures."""


@dataclass(slots=True)
class HomeParameters:
    travel_limit: int = 500
    max_velocity: int = 20
    run_current: int = 50
    stall_threshold: int = 10

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (
            self.travel_limit,
            self.max_velocity,
            self.run_current,
            self.stall_threshold,
        )

    def __str__(self) -> str:
        return "\n".join(f"{key} = {value}" for key, value in asdict(self).items()) + "\n"


@dataclass(slots=True)
class ControllerParameters:
    start_velocity: int = 1
    stop_velocity: int = 5
    first_velocity: int = 10
    max_velocity: int = 20
    first_acceleration: int = 40
    max_acceleration: int = 20
    max_deceleration: int = 30
    first_deceleration: int = 50

    def to_tuple(self) -> tuple[int, int, int, int, int, int, int, int]:
        return (
            self.start_velocity,
            self.stop_velocity,
            self.first_velocity,
            self.max_velocity,
            self.first_acceleration,
            self.max_acceleration,
            self.max_deceleration,
            self.first_deceleration,
        )

    def __str__(self) -> str:
        return "\n".join(f"{key} = {value}" for key, value in asdict(self).items()) + "\n"


def results_filter(pair: tuple[str, Any]) -> bool:
    """Return True when an nmap result exposes the hex-maze TCP port."""
    key, value = pair
    del key
    try:
        ports = value["ports"]
        return any(
            port["portid"] == str(HexMazeInterface.PORT) and port["state"] == "open"
            for port in ports
        )
    except (KeyError, TypeError):
        return False


class HexMazeInterface:
    PORT = 7777
    IP_BASE = "192.168.10."
    IP_RANGE = IP_BASE + "0/24"
    REPEAT_LIMIT = 2
    PROTOCOL_VERSION = 0x04
    ERROR_RESPONSE = 0xEE
    CHECK_COMMUNICATION_RESPONSE = 0x12345678
    CLUSTER_ADDRESS_MIN = 10
    CLUSTER_ADDRESS_MAX = 17
    CLUSTER_ADDRESSES = tuple(range(CLUSTER_ADDRESS_MIN, CLUSTER_ADDRESS_MAX))
    CLUSTER_COUNT = len(CLUSTER_ADDRESSES)
    PRISM_COUNT = 7
    PROTOCOL_VERSION_INDEX = 0
    LENGTH_INDEX = 1
    COMMAND_NUMBER_INDEX = 2
    FIRST_PARAMETER_INDEX = 3

    def __init__(
        self,
        debug: bool = False,
        *,
        timeout_s: float | None = SOCKET_TIMEOUT_S,
        discover_backend: Any | None = None,
        sleep_fn: Any = time.sleep,
    ):
        self._debug = bool(debug)
        self._timeout_s = None if timeout_s is None else float(timeout_s)
        self._discover_backend = discover_backend
        self._sleep_fn = sleep_fn
        self._cluster_addresses: list[int] = []

    def __enter__(self) -> HexMazeInterface:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def close(self) -> None:
        """Present for interface symmetry; sockets are opened per request."""

    def _debug_print(self, *args: Any) -> None:
        if self._debug:
            print(*args)

    @staticmethod
    def _cluster_ip(cluster_address: int) -> str:
        return f"{HexMazeInterface.IP_BASE}{cluster_address}"

    @staticmethod
    def _validate_cluster_address(cluster_address: int) -> None:
        if cluster_address not in HexMazeInterface.CLUSTER_ADDRESSES:
            raise MazeException(
                f"cluster_address must be in {HexMazeInterface.CLUSTER_ADDRESS_MIN}"
                f"..{HexMazeInterface.CLUSTER_ADDRESS_MAX - 1}: {cluster_address}"
            )

    @staticmethod
    def _validate_prism_address(prism_address: int) -> None:
        if not 0 <= int(prism_address) < HexMazeInterface.PRISM_COUNT:
            raise MazeException(
                f"prism_address must be in 0..{HexMazeInterface.PRISM_COUNT - 1}: {prism_address}"
            )

    @staticmethod
    def _validate_sequence(name: str, values: Any, expected_len: int) -> tuple[Any, ...]:
        try:
            normalized = tuple(values)
        except TypeError as exc:
            raise MazeException(f"{name} must be iterable") from exc
        if len(normalized) != expected_len:
            raise MazeException(f"{name} must contain {expected_len} values, got {len(normalized)}")
        return normalized

    @staticmethod
    def _flatten_pairs(name: str, values: Any, expected_len: int) -> tuple[Any, ...]:
        normalized = HexMazeInterface._validate_sequence(name, values, expected_len)
        flattened: list[Any] = []
        for index, pair in enumerate(normalized):
            pair_values = HexMazeInterface._validate_sequence(f"{name}[{index}]", pair, 2)
            flattened.extend(pair_values)
        return tuple(flattened)

    @staticmethod
    def _nmap_backend(discover_backend: Any | None) -> Any:
        if discover_backend is not None:
            return discover_backend
        if nmap3 is None:
            raise MazeException(
                "cluster discovery requires the optional dependency 'python3-nmap'"
            )
        return nmap3.NmapHostDiscovery()

    @staticmethod
    def _encode_command(
        command_format: str,
        command_length: int,
        command_number: int | None = None,
        command_parameters: Any = None,
    ) -> bytes:
        fields: list[Any] = [HexMazeInterface.PROTOCOL_VERSION, command_length]
        if command_number is not None:
            fields.append(command_number)
        if command_parameters is not None:
            if isinstance(command_parameters, tuple):
                fields.extend(command_parameters)
            else:
                fields.append(command_parameters)
        try:
            return struct.pack(command_format, *fields)
        except struct.error as exc:
            payload = {
                "format": command_format,
                "length": command_length,
                "command_number": command_number,
                "parameters": command_parameters,
            }
            raise MazeException(f"failed to encode command: {json.dumps(payload, default=str)}") from exc

    @classmethod
    def _validate_response(cls, response_bytes: bytes, expected_command_number: int) -> bytes:
        if len(response_bytes) < cls.FIRST_PARAMETER_INDEX:
            raise MazeException(f"response too short: {len(response_bytes)} bytes")

        protocol_version = response_bytes[cls.PROTOCOL_VERSION_INDEX]
        if protocol_version != cls.PROTOCOL_VERSION:
            raise MazeException(f"response protocol-version is not {cls.PROTOCOL_VERSION}")

        reported_response_length = response_bytes[cls.LENGTH_INDEX]
        measured_response_length = len(response_bytes)
        if measured_response_length != reported_response_length:
            raise MazeException(
                f"response length is {measured_response_length} not {reported_response_length}"
            )

        response_command_number = response_bytes[cls.COMMAND_NUMBER_INDEX]
        if response_command_number == cls.ERROR_RESPONSE:
            raise MazeException("received error response")
        if response_command_number != expected_command_number:
            raise MazeException(
                "response command-number is "
                f"{response_command_number} not {expected_command_number}"
            )

        return response_bytes[cls.FIRST_PARAMETER_INDEX :]

    @classmethod
    def _decode_response_parameters(
        cls,
        response_parameter_bytes: bytes,
        response_parameters_format: str,
        response_parameters_length: int,
    ) -> Any:
        if len(response_parameter_bytes) != response_parameters_length:
            raise MazeException(
                "response parameter length is "
                f"{len(response_parameter_bytes)} not {response_parameters_length}"
            )

        if response_parameters_length == 0:
            return ()

        unpacked = struct.unpack(response_parameters_format, response_parameter_bytes)
        if len(unpacked) == 1:
            return unpacked[0]
        return unpacked

    def _discover_ip_addresses(self) -> list[str]:
        backend = self._nmap_backend(self._discover_backend)
        results = backend.nmap_portscan_only(self.IP_RANGE, args=f"-p {self.PORT}")
        filtered_results = dict(filter(results_filter, results.items()))
        return sorted(filtered_results.keys(), key=lambda ip: tuple(int(part) for part in ip.split(".")))

    def discover_cluster_addresses(self) -> list[int]:
        self._cluster_addresses = [int(ip_address.split(".")[-1]) for ip_address in self._discover_ip_addresses()]
        return list(self._cluster_addresses)

    def _send_ip_cmd_bytes_receive_rsp_params_bytes(self, ip_address: str, cmd_bytes: bytes) -> bytes:
        repeat_count = 0
        last_error: BaseException | None = None
        self._debug_print("cmd_bytes:", cmd_bytes.hex())

        while repeat_count < self.REPEAT_LIMIT:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    self._debug_print(f"to {ip_address} port {self.PORT}")
                    sock.settimeout(self._timeout_s)
                    sock.connect((ip_address, self.PORT))
                    sock.sendall(cmd_bytes)
                    rsp_bytes = sock.recv(1024)
                    self._debug_print("rsp_bytes:", rsp_bytes.hex())
                    expected_command_number = cmd_bytes[self.COMMAND_NUMBER_INDEX]
                    return self._validate_response(rsp_bytes, expected_command_number)
            except (TimeoutError, OSError) as exc:
                last_error = exc
                repeat_count += 1
                self._debug_print("socket attempt failed:", exc)

        if last_error is None:
            raise MazeException("no response received")
        raise MazeException(f"no response received: {type(last_error).__name__}: {last_error}")

    def _send_cluster_cmd_receive_rsp_params(
        self,
        cluster_address: int,
        cmd_fmt: str,
        cmd_len: int,
        cmd_num: int,
        cmd_par: Any = None,
        rsp_params_fmt: str = "",
        rsp_params_len: int = 0,
    ) -> Any:
        self._validate_cluster_address(cluster_address)
        cmd_bytes = self._encode_command(cmd_fmt, cmd_len, cmd_num, cmd_par)
        rsp_params_bytes = self._send_ip_cmd_bytes_receive_rsp_params_bytes(
            self._cluster_ip(cluster_address),
            cmd_bytes,
        )
        return self._decode_response_parameters(rsp_params_bytes, rsp_params_fmt, rsp_params_len)

    def _bool_command(
        self,
        cluster_address: int,
        cmd_fmt: str,
        cmd_len: int,
        cmd_num: int,
        cmd_par: Any = None,
        rsp_params_fmt: str = "",
        rsp_params_len: int = 0,
    ) -> bool:
        try:
            self._send_cluster_cmd_receive_rsp_params(
                cluster_address,
                cmd_fmt,
                cmd_len,
                cmd_num,
                cmd_par,
                rsp_params_fmt,
                rsp_params_len,
            )
            return True
        except MazeException:
            return False

    def no_cmd(self, cluster_address: int) -> None:
        self._validate_cluster_address(cluster_address)
        cmd_bytes = self._encode_command("<BB", 2)
        self._send_ip_cmd_bytes_receive_rsp_params_bytes(self._cluster_ip(cluster_address), cmd_bytes)

    def bad_cmd(self, cluster_address: int) -> None:
        self._send_cluster_cmd_receive_rsp_params(cluster_address, "<BBB", 3, self.ERROR_RESPONSE)

    def read_cluster_address(self, ip_address: str) -> int:
        cmd_bytes = self._encode_command("<BBB", 3, 0x01)
        rsp_params_bytes = self._send_ip_cmd_bytes_receive_rsp_params_bytes(ip_address, cmd_bytes)
        return self._decode_response_parameters(rsp_params_bytes, "<B", 1)

    def communicating_cluster(self, cluster_address: int) -> bool:
        try:
            communication_response = self._send_cluster_cmd_receive_rsp_params(
                cluster_address,
                "<BBB",
                3,
                0x02,
                None,
                "<L",
                4,
            )
            return communication_response == self.CHECK_COMMUNICATION_RESPONSE
        except MazeException:
            return False

    def communicating_all_clusters(self) -> list[bool]:
        return [self.communicating_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def reset_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x03)

    def reset_all_clusters(self) -> list[bool]:
        return [self.reset_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def beep_cluster(self, cluster_address: int, duration_ms: int) -> bool:
        ok = self._bool_command(cluster_address, "<BBBH", 5, 0x04, int(duration_ms))
        if ok:
            self._sleep_fn(duration_ms / MILLISECONDS_PER_SECOND)
        return ok

    def beep_all_clusters(self, duration_ms: int) -> list[bool]:
        return [self.beep_cluster(cluster_address, duration_ms) for cluster_address in self.CLUSTER_ADDRESSES]

    def led_off_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x05)

    def led_off_all_clusters(self) -> list[bool]:
        return [self.led_off_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def led_on_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x06)

    def led_on_all_clusters(self) -> list[bool]:
        return [self.led_on_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def measure_communication_cluster(self, cluster_address: int, repeat_count: int) -> float:
        time_begin = time.time()
        for _ in range(repeat_count):
            self.led_on_then_off_cluster(cluster_address)
        time_end = time.time()
        duration = (time_end - time_begin) / (repeat_count * 2)
        self._debug_print("duration =", duration)
        return duration

    def led_on_then_off_cluster(self, cluster_address: int) -> None:
        self.led_on_cluster(cluster_address)
        self.led_off_cluster(cluster_address)

    def power_off_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x07)

    def power_off_all_clusters(self) -> list[bool]:
        return [self.power_off_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def power_on_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x08)

    def power_on_all_clusters(self) -> list[bool]:
        return [self.power_on_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def home_prism(
        self,
        cluster_address: int,
        prism_address: int,
        home_parameters: HomeParameters,
    ) -> bool:
        self._validate_prism_address(prism_address)
        cmd_par = (prism_address, *home_parameters.to_tuple())
        return self._bool_command(cluster_address, "<BBBBHBBb", 9, 0x09, cmd_par, "<B", 1)

    def home_cluster(self, cluster_address: int, home_parameters: HomeParameters) -> bool:
        return self._bool_command(cluster_address, "<BBBHBBb", 8, 0x0A, home_parameters.to_tuple())

    def home_all_clusters(self, home_parameters: HomeParameters) -> list[bool]:
        return [self.home_cluster(cluster_address, home_parameters) for cluster_address in self.CLUSTER_ADDRESSES]

    def homed_cluster(self, cluster_address: int) -> tuple[int, ...]:
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, "<BBB", 3, 0x0B, None, "<BBBBBBB", 7)

    def write_target_prism(self, cluster_address: int, prism_address: int, position_mm: int) -> bool:
        self._validate_prism_address(prism_address)
        return self._bool_command(cluster_address, "<BBBBH", 6, 0x0C, (prism_address, position_mm), "<B", 1)

    def write_targets_cluster(self, cluster_address: int, positions_mm: Any) -> bool:
        positions = self._validate_sequence("positions_mm", positions_mm, self.PRISM_COUNT)
        return self._bool_command(cluster_address, "<BBBHHHHHHH", 17, 0x0D, positions)

    def pause_prism(self, cluster_address: int, prism_address: int) -> bool:
        self._validate_prism_address(prism_address)
        return self._bool_command(cluster_address, "<BBBB", 4, 0x0E, prism_address, "<B", 1)

    def pause_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x0F)

    def pause_all_clusters(self) -> list[bool]:
        return [self.pause_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def resume_prism(self, cluster_address: int, prism_address: int) -> bool:
        self._validate_prism_address(prism_address)
        return self._bool_command(cluster_address, "<BBBB", 4, 0x10, prism_address, "<B", 1)

    def resume_cluster(self, cluster_address: int) -> bool:
        return self._bool_command(cluster_address, "<BBB", 3, 0x11)

    def resume_all_clusters(self) -> list[bool]:
        return [self.resume_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]

    def read_positions_cluster(self, cluster_address: int) -> tuple[int, ...]:
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, "<BBB", 3, 0x12, None, "<hhhhhhh", 14)

    def write_run_current_cluster(self, cluster_address: int, current_percent: int) -> bool:
        return self._bool_command(cluster_address, "<BBBB", 4, 0x13, current_percent)

    def read_run_current_cluster(self, cluster_address: int) -> int:
        return self._send_cluster_cmd_receive_rsp_params(cluster_address, "<BBB", 3, 0x14, None, "<B", 1)

    def write_run_current_all_clusters(self, current_percent: int) -> list[bool]:
        return [self.write_run_current_cluster(cluster_address, current_percent) for cluster_address in self.CLUSTER_ADDRESSES]

    def write_controller_parameters_cluster(
        self,
        cluster_address: int,
        controller_parameters: ControllerParameters,
    ) -> bool:
        return self._bool_command(
            cluster_address,
            "<BBBBBBBBBBB",
            11,
            0x15,
            controller_parameters.to_tuple(),
        )

    def read_controller_parameters_cluster(self, cluster_address: int) -> ControllerParameters:
        controller_parameters_tuple = self._send_cluster_cmd_receive_rsp_params(
            cluster_address,
            "<BBB",
            3,
            0x16,
            None,
            "<BBBBBBBB",
            8,
        )
        return ControllerParameters(*controller_parameters_tuple)

    def write_controller_parameters_all_clusters(
        self,
        controller_parameters: ControllerParameters,
    ) -> list[bool]:
        return [
            self.write_controller_parameters_cluster(cluster_address, controller_parameters)
            for cluster_address in self.CLUSTER_ADDRESSES
        ]

    def write_double_target_prism(
        self,
        cluster_address: int,
        prism_address: int,
        double_position_mm: Any,
    ) -> bool:
        self._validate_prism_address(prism_address)
        positions = self._validate_sequence("double_position_mm", double_position_mm, 2)
        return self._bool_command(cluster_address, "<BBBBHH", 8, 0x17, (prism_address, *positions), "<B", 1)

    def write_double_targets_cluster(self, cluster_address: int, double_positions_mm: Any) -> bool:
        flattened = self._flatten_pairs("double_positions_mm", double_positions_mm, self.PRISM_COUNT)
        return self._bool_command(
            cluster_address,
            "<BBBHHHHHHHHHHHHHH",
            31,
            0x18,
            flattened,
        )

    def verify_cluster(self, cluster_address: int) -> dict[str, Any]:
        """Run a non-destructive firmware smoke check for one cluster."""
        report: dict[str, Any] = {
            "cluster_address": cluster_address,
            "ok": False,
            "checks": {},
        }

        try:
            communicating = self.communicating_cluster(cluster_address)
            report["checks"]["communicating"] = communicating
            if not communicating:
                report["error"] = "communication check failed"
                return report

            report["checks"]["homed"] = list(self.homed_cluster(cluster_address))
            report["checks"]["positions_mm"] = list(self.read_positions_cluster(cluster_address))
            report["checks"]["run_current_percent"] = self.read_run_current_cluster(cluster_address)
            report["checks"]["controller_parameters"] = asdict(
                self.read_controller_parameters_cluster(cluster_address)
            )
            report["ok"] = True
            return report
        except MazeException as exc:
            report["error"] = str(exc)
            return report

    def verify_all_clusters(self) -> list[dict[str, Any]]:
        return [self.verify_cluster(cluster_address) for cluster_address in self.CLUSTER_ADDRESSES]
