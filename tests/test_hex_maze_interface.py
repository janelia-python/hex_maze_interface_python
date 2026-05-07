from __future__ import annotations

import struct

import pytest

from hex_maze_interface.hex_maze_interface import (
    POWER_ON_SETTLE_S,
    ControllerParameters,
    HexMazeInterface,
    HomeOutcome,
    HomeParameters,
    MazeException,
    PrismDiagnostics,
)


def test_encode_command_with_tuple_parameters() -> None:
    command = HexMazeInterface._encode_command(
        "<BBBBHBBb",
        9,
        0x09,
        (2, 100, 20, 50, 10),
    )

    assert command == struct.pack(
        "<BBBBHBBb",
        HexMazeInterface.PROTOCOL_VERSION,
        9,
        0x09,
        2,
        100,
        20,
        50,
        10,
    )


def test_validate_response_rejects_wrong_command() -> None:
    with pytest.raises(MazeException, match="response command-number is 17 not 16"):
        HexMazeInterface._validate_response(
            bytes((HexMazeInterface.PROTOCOL_VERSION, 3, 17)),
            16,
        )


def test_write_targets_cluster_validates_prism_count() -> None:
    hmi = HexMazeInterface()

    with pytest.raises(MazeException, match="positions_mm must contain 7 values, got 2"):
        hmi.write_targets_cluster(10, (1, 2))


def test_write_double_targets_cluster_validates_pair_structure() -> None:
    hmi = HexMazeInterface()

    with pytest.raises(
        MazeException,
        match="double_positions_mm\\[0\\] must contain 2 values, got 1",
    ):
        hmi.write_double_targets_cluster(
            10,
            ((1,), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13)),
        )


def test_verify_cluster_collects_non_destructive_status() -> None:
    hmi = HexMazeInterface()

    hmi.communicating_cluster = lambda cluster_address: True
    hmi.homed_cluster = lambda cluster_address: (1, 1, 1, 1, 1, 1, 1)
    hmi.read_home_outcomes_cluster = lambda cluster_address: (HomeOutcome.CONFIRMED,) * 7
    hmi.read_positions_cluster = lambda cluster_address: (10, 20, 30, 40, 50, 60, 70)
    hmi.read_run_current_cluster = lambda cluster_address: 80
    hmi.read_controller_parameters_cluster = lambda cluster_address: ControllerParameters()
    hmi.read_prism_diagnostics_cluster = lambda cluster_address: (
        (PrismDiagnostics.from_wire(0x01, 0x00, 0, 0, 0),) * HexMazeInterface.PRISM_COUNT
    )

    report = hmi.verify_cluster(10)

    assert report["ok"] is True
    assert report["cluster_address"] == 10
    assert report["checks"]["home_outcomes"] == ["CONFIRMED"] * 7
    assert report["checks"]["positions_mm"] == [10, 20, 30, 40, 50, 60, 70]
    assert report["checks"]["run_current_percent"] == 80
    assert report["checks"]["controller_parameters"]["max_velocity"] == 40
    assert report["checks"]["prism_diagnostics"][0]["communicating"] is True


def test_read_prism_diagnostics_cluster_decodes_fault_flags() -> None:
    hmi = HexMazeInterface()
    hmi._send_cluster_cmd_receive_rsp_params = lambda *args, **kwargs: (
        (
            0b01111111,
            0b01111110,
            513,
            17,
            42,
        )
        + (0, 0, 0, 0, 0) * (HexMazeInterface.PRISM_COUNT - 1)
    )

    diagnostics = hmi.read_prism_diagnostics_cluster(10)

    assert diagnostics[0].communicating is True
    assert diagnostics[0].reset_latched is True
    assert diagnostics[0].driver_error_latched is True
    assert diagnostics[0].over_temperature_warning is True
    assert diagnostics[0].short_to_ground_a is True
    assert diagnostics[0].open_load_b is True
    assert diagnostics[0].stall_guard_result == 513
    assert diagnostics[0].current_scale == 17
    assert diagnostics[0].last_home_travel_mm == 42
    assert diagnostics[0].has_fault() is True
    assert diagnostics[1].has_fault() is False


def test_recovery_home_prism_uses_recovery_command() -> None:
    hmi = HexMazeInterface()
    calls = []
    hmi._bool_command = lambda *args, **kwargs: calls.append((args, kwargs)) or True

    ok = hmi.recovery_home_prism(10, 2, HomeParameters(550, 10, 40, 0))

    assert ok is True
    assert calls == [((10, "<BBBBHBBb", 9, 0x1C, (2, 550, 10, 40, 0), "<B", 1), {})]


def test_recovery_home_cluster_uses_recovery_command() -> None:
    hmi = HexMazeInterface()
    calls = []
    hmi._bool_command = lambda *args, **kwargs: calls.append((args, kwargs)) or True

    ok = hmi.recovery_home_cluster(10, HomeParameters(550, 10, 40, 0))

    assert ok is True
    assert calls == [((10, "<BBBHBBb", 8, 0x1D, (550, 10, 40, 0)), {})]


def test_confirm_home_prism_uses_confirm_command() -> None:
    hmi = HexMazeInterface()
    calls = []
    hmi._bool_command = lambda *args, **kwargs: calls.append((args, kwargs)) or True

    ok = hmi.confirm_home_prism(10, 2)

    assert ok is True
    assert calls == [((10, "<BBBB", 4, 0x1E, 2, "<B", 1), {})]


def test_confirm_home_cluster_uses_confirm_command() -> None:
    hmi = HexMazeInterface()
    calls = []
    hmi._bool_command = lambda *args, **kwargs: calls.append((args, kwargs)) or True

    ok = hmi.confirm_home_cluster(10)

    assert ok is True
    assert calls == [((10, "<BBB", 3, 0x1F), {})]


def test_home_parameters_string_format() -> None:
    params = HomeParameters()

    assert "travel_limit = 100" in str(params)


def test_read_home_outcomes_cluster_decodes_enum_values() -> None:
    hmi = HexMazeInterface()
    hmi._send_cluster_cmd_receive_rsp_params = lambda *args, **kwargs: (0, 1, 2, 3, 4, 0, 2)

    outcomes = hmi.read_home_outcomes_cluster(10)

    assert outcomes == (
        HomeOutcome.NONE,
        HomeOutcome.IN_PROGRESS,
        HomeOutcome.STALL,
        HomeOutcome.TARGET_REACHED,
        HomeOutcome.FAILED,
        HomeOutcome.NONE,
        HomeOutcome.STALL,
    )


def test_read_home_outcomes_cluster_decodes_confirmed_value() -> None:
    hmi = HexMazeInterface()
    hmi._send_cluster_cmd_receive_rsp_params = lambda *args, **kwargs: (5, 0, 0, 0, 0, 0, 0)

    outcomes = hmi.read_home_outcomes_cluster(10)

    assert outcomes[0] == HomeOutcome.CONFIRMED


def test_power_on_cluster_waits_for_prism_settle() -> None:
    sleep_calls: list[float] = []
    hmi = HexMazeInterface(sleep_fn=sleep_calls.append)
    hmi._bool_command = lambda *args, **kwargs: True

    ok = hmi.power_on_cluster(10)

    assert ok is True
    assert sleep_calls == [POWER_ON_SETTLE_S]


def test_power_on_cluster_does_not_sleep_on_failure() -> None:
    sleep_calls: list[float] = []
    hmi = HexMazeInterface(sleep_fn=sleep_calls.append)
    hmi._bool_command = lambda *args, **kwargs: False

    ok = hmi.power_on_cluster(10)

    assert ok is False
    assert sleep_calls == []
