#!/usr/bin/env python3
"""Hardware edge-case regression test for a live cluster."""

from __future__ import annotations

import argparse
import json
import random
import time

from hex_maze_interface import (
    ControllerParameters,
    HexMazeInterface,
    HomeOutcome,
    HomeParameters,
    MazeException,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--prism", type=int, default=0, help="Primary prism for per-prism tests.")
    parser.add_argument("--initial-travel-limit", type=int, default=100)
    parser.add_argument("--travel-limit", type=int, default=100)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--home-repeat-count", type=int, default=3)
    parser.add_argument("--queue-overflow-count", type=int, default=6)
    parser.add_argument("--distributed-move-low", type=int, default=40)
    parser.add_argument("--distributed-move-high", type=int, default=180)
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _wait_for_positions(
    hmi: HexMazeInterface,
    cluster_address: int,
    targets_mm: tuple[int, ...],
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
) -> tuple[int, ...]:
    deadline = time.monotonic() + timeout_s
    last_positions = tuple(hmi.read_positions_cluster(cluster_address))
    while time.monotonic() < deadline:
        last_positions = tuple(hmi.read_positions_cluster(cluster_address))
        if all(
            abs(position - target) <= tolerance_mm
            for position, target in zip(last_positions, targets_mm, strict=True)
        ):
            return last_positions
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} did not reach targets {list(targets_mm)}; "
        f"last positions were {list(last_positions)}"
    )


def _wait_for_prism_position(
    hmi: HexMazeInterface,
    cluster_address: int,
    prism_address: int,
    target_mm: int,
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
) -> int:
    deadline = time.monotonic() + timeout_s
    last_position = tuple(hmi.read_positions_cluster(cluster_address))[prism_address]
    while time.monotonic() < deadline:
        last_position = tuple(hmi.read_positions_cluster(cluster_address))[prism_address]
        if abs(last_position - target_mm) <= tolerance_mm:
            return last_position
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} prism {prism_address} did not reach target {target_mm}; "
        f"last position was {last_position}"
    )


def _wait_for_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    last = {
        "homed": tuple(hmi.homed_cluster(cluster_address)),
        "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
        "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
    }
    while time.monotonic() < deadline:
        last = {
            "homed": tuple(hmi.homed_cluster(cluster_address)),
            "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
            "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
        }
        if all(outcome != HomeOutcome.IN_PROGRESS for outcome in last["outcomes"]):
            return {
                "homed": list(last["homed"]),
                "outcomes": [outcome.name for outcome in last["outcomes"]],
                "positions_mm": list(last["positions_mm"]),
            }
        if any(outcome == HomeOutcome.FAILED for outcome in last["outcomes"]):
            raise MazeException(
                f"cluster {cluster_address} reported failed home outcome: "
                f"{[outcome.name for outcome in last['outcomes']]}"
            )
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish homing; last state was {last}")


def _ensure_cluster_is_alive(hmi: HexMazeInterface, cluster_address: int) -> dict[str, object]:
    verify_report = hmi.verify_cluster(cluster_address)
    if not verify_report["checks"].get("communicating", False):
        raise MazeException(f"cluster {cluster_address} failed communication check")
    return verify_report


def _assert_all_prisms_visible(positions_mm: tuple[int, ...]) -> None:
    missing = [index for index, position in enumerate(positions_mm) if position < 0]
    if missing:
        raise MazeException(
            f"non-communicating prisms reported positions < 0 at addresses {missing}"
        )


def _assert_all_homed(report: dict[str, object]) -> None:
    homed = list(report["homed"])
    outcomes = list(report["outcomes"])
    if not all(homed):
        raise MazeException(f"expected all prisms homed, got homed={homed}")
    if any(
        outcome not in (HomeOutcome.STALL.name, HomeOutcome.TARGET_REACHED.name)
        for outcome in outcomes
    ):
        raise MazeException(f"expected terminal home outcomes, got {outcomes}")


def _home_until_all_homed(
    hmi: HexMazeInterface,
    cluster_address: int,
    home_parameters: HomeParameters,
    timeout_s: float,
    poll_interval_s: float,
    max_attempts: int,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for attempt_index in range(max_attempts):
        if not hmi.home_cluster(cluster_address, home_parameters):
            raise MazeException(
                f"cluster {cluster_address} failed to start homing on attempt {attempt_index}"
            )
        report = _wait_for_home(hmi, cluster_address, timeout_s, poll_interval_s)
        reports.append(report)
        if all(report["homed"]):
            return reports
    raise MazeException(
        f"cluster {cluster_address} did not fully home after {max_attempts} attempts: {reports[-1]}"
    )


def _power_cycle(hmi: HexMazeInterface, cluster_address: int) -> dict[str, object]:
    if not hmi.power_off_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} failed power_off_cluster")
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} failed power_on_cluster")
    verify_report = _ensure_cluster_is_alive(hmi, cluster_address)
    positions = tuple(verify_report["checks"]["positions_mm"])
    _assert_all_prisms_visible(positions)
    return verify_report


def _initial_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    home_parameters = HomeParameters(
        travel_limit=args.initial_travel_limit,
        max_velocity=10,
        run_current=43,
        stall_threshold=0,
    )
    return _home_until_all_homed(
        hmi,
        cluster_address,
        home_parameters,
        args.home_timeout,
        args.poll_interval,
        3,
    )


def _repeat_home_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    move_targets = tuple(80 + 5 * prism_address for prism_address in range(hmi.PRISM_COUNT))
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=10,
        run_current=43,
        stall_threshold=0,
    )

    for cycle_index in range(args.home_repeat_count):
        if cycle_index == 0:
            if not hmi.write_targets_cluster(cluster_address, move_targets):
                raise MazeException("failed to stage pre-home cluster move")
            _wait_for_positions(
                hmi,
                cluster_address,
                move_targets,
                args.position_timeout,
                args.poll_interval,
                args.position_tolerance,
            )

        report = _home_until_all_homed(
            hmi,
            cluster_address,
            home_parameters,
            args.home_timeout,
            args.poll_interval,
            2,
        )[-1]
        _assert_all_homed(report)
        results.append(report)

    return results


def _command_during_home_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    injected_targets = tuple(130 + 10 * prism_address for prism_address in range(hmi.PRISM_COUNT))
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=10,
        run_current=43,
        stall_threshold=0,
    )

    if not hmi.home_cluster(cluster_address, home_parameters):
        raise MazeException("command-during-home: home_cluster failed")
    if not hmi.write_targets_cluster(cluster_address, injected_targets):
        raise MazeException("command-during-home: write_targets_cluster failed")

    report = _home_until_all_homed(
        hmi,
        cluster_address,
        home_parameters,
        args.home_timeout,
        args.poll_interval,
        2,
    )[-1]
    _assert_all_homed(report)
    final_positions = tuple(report["positions_mm"])
    if any(abs(position) > args.position_tolerance for position in final_positions):
        raise MazeException(
            "command-during-home targets were not discarded; "
            f"positions after home were {list(final_positions)}"
        )

    return {
        "injected_targets_mm": list(injected_targets),
        "home": report,
    }


def _pause_resume_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    prism_address = args.prism
    move_target = 180
    queue_targets = (90, 140, 190)

    if not hmi.write_target_prism(cluster_address, prism_address, move_target):
        raise MazeException("pause-resume: initial move command failed")
    time.sleep(min(0.5, args.poll_interval * 2))

    if not hmi.pause_prism(cluster_address, prism_address):
        raise MazeException("pause-resume: pause_prism failed")

    paused_before = tuple(hmi.read_positions_cluster(cluster_address))[prism_address]
    time.sleep(0.75)
    paused_after = tuple(hmi.read_positions_cluster(cluster_address))[prism_address]
    if abs(paused_after - paused_before) > args.position_tolerance:
        raise MazeException(
            f"pause-resume: prism moved while paused ({paused_before} -> {paused_after})"
        )

    for target in queue_targets:
        if not hmi.write_target_prism(cluster_address, prism_address, target):
            raise MazeException(
                f"pause-resume: queued write_target_prism failed for target {target}"
            )

    if not hmi.resume_prism(cluster_address, prism_address):
        raise MazeException("pause-resume: resume_prism failed")

    final_position = _wait_for_prism_position(
        hmi,
        cluster_address,
        prism_address,
        queue_targets[-1],
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    return {
        "prism_address": prism_address,
        "paused_position_mm": paused_after,
        "queued_targets_mm": list(queue_targets),
        "final_position_mm": final_position,
    }


def _queue_overflow_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    prism_address = args.prism
    queued_targets = [40 + 20 * index for index in range(args.queue_overflow_count)]
    expected_targets = queued_targets[:4]

    if not hmi.pause_prism(cluster_address, prism_address):
        raise MazeException("queue-overflow: pause_prism failed")
    for target in queued_targets:
        if not hmi.write_target_prism(cluster_address, prism_address, target):
            raise MazeException(f"queue-overflow: write_target_prism failed for target {target}")
    if not hmi.resume_prism(cluster_address, prism_address):
        raise MazeException("queue-overflow: resume_prism failed")

    observed_targets: list[int] = []
    for target in expected_targets:
        observed_targets.append(
            _wait_for_prism_position(
                hmi,
                cluster_address,
                prism_address,
                target,
                args.position_timeout,
                args.poll_interval,
                args.position_tolerance,
            )
        )

    positions_after_drain = tuple(hmi.read_positions_cluster(cluster_address))
    final_position = positions_after_drain[prism_address]
    if abs(final_position - expected_targets[-1]) > args.position_tolerance:
        raise MazeException(
            "queue-overflow: final position indicates extra queued targets executed; "
            f"expected about {expected_targets[-1]}, got {final_position}"
        )

    return {
        "prism_address": prism_address,
        "requested_targets_mm": queued_targets,
        "expected_executed_targets_mm": expected_targets,
        "observed_targets_mm": observed_targets,
        "final_position_mm": final_position,
    }


def _distributed_cluster_motion_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    if args.distributed_move_low >= args.distributed_move_high:
        raise MazeException("--distributed-move-low must be less than --distributed-move-high")

    rng = random.Random(args.seed + cluster_address)
    requested_targets = tuple(
        rng.randint(args.distributed_move_low, args.distributed_move_high)
        for _ in range(hmi.PRISM_COUNT)
    )
    if not hmi.write_targets_cluster(cluster_address, requested_targets):
        raise MazeException("distributed-cluster-motion: write_targets_cluster failed")
    observed_positions = _wait_for_positions(
        hmi,
        cluster_address,
        requested_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    return {
        "requested_targets_mm": list(requested_targets),
        "observed_positions_mm": list(observed_positions),
    }


def _final_cleanup_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=10,
        run_current=43,
        stall_threshold=0,
    )
    report = _home_until_all_homed(
        hmi,
        cluster_address,
        home_parameters,
        args.home_timeout,
        args.poll_interval,
        2,
    )[-1]
    _assert_all_homed(report)
    return report


def _parameter_persistence_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    default_run_current = 75
    default_controller_parameters = ControllerParameters()
    run_current = 61
    controller_parameters = ControllerParameters(2, 6, 11, 21, 41, 22, 31, 51)
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=10,
        run_current=43,
        stall_threshold=0,
    )

    if not hmi.write_run_current_cluster(cluster_address, run_current):
        raise MazeException("parameter-persistence: write_run_current_cluster failed")
    if not hmi.write_controller_parameters_cluster(cluster_address, controller_parameters):
        raise MazeException("parameter-persistence: write_controller_parameters_cluster failed")

    before_home = {
        "run_current_percent": hmi.read_run_current_cluster(cluster_address),
        "controller_parameters": hmi.read_controller_parameters_cluster(cluster_address).to_tuple(),
    }

    if before_home["run_current_percent"] != run_current:
        raise MazeException(
            "parameter-persistence: run current readback mismatch before home: "
            f"{before_home['run_current_percent']}"
        )
    if before_home["controller_parameters"] != controller_parameters.to_tuple():
        raise MazeException(
            "parameter-persistence: controller parameter readback mismatch before home: "
            f"{before_home['controller_parameters']}"
        )

    home_report = _home_until_all_homed(
        hmi,
        cluster_address,
        home_parameters,
        args.home_timeout,
        args.poll_interval,
        2,
    )[-1]
    _assert_all_homed(home_report)

    after_home = {
        "run_current_percent": hmi.read_run_current_cluster(cluster_address),
        "controller_parameters": hmi.read_controller_parameters_cluster(cluster_address).to_tuple(),
        "home_positions_mm": home_report["positions_mm"],
    }

    if not hmi.power_off_cluster(cluster_address):
        raise MazeException("parameter-persistence: power_off_cluster failed")
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException("parameter-persistence: power_on_cluster failed")
    _ensure_cluster_is_alive(hmi, cluster_address)

    after_power_cycle = {
        "run_current_percent": hmi.read_run_current_cluster(cluster_address),
        "controller_parameters": hmi.read_controller_parameters_cluster(cluster_address).to_tuple(),
    }

    if (
        after_home["run_current_percent"] != run_current
        or after_power_cycle["run_current_percent"] != run_current
    ):
        raise MazeException(
            "parameter-persistence: run current did not persist across home/power cycle"
        )
    if (
        after_home["controller_parameters"] != controller_parameters.to_tuple()
        or after_power_cycle["controller_parameters"] != controller_parameters.to_tuple()
    ):
        raise MazeException(
            "parameter-persistence: controller parameters did not persist across home/power cycle"
        )

    if not hmi.write_run_current_cluster(cluster_address, default_run_current):
        raise MazeException("parameter-persistence: failed to restore default run current")
    if not hmi.write_controller_parameters_cluster(cluster_address, default_controller_parameters):
        raise MazeException(
            "parameter-persistence: failed to restore default controller parameters"
        )

    return {
        "written_run_current_percent": run_current,
        "written_controller_parameters": list(controller_parameters.to_tuple()),
        "restored_run_current_percent": default_run_current,
        "restored_controller_parameters": list(default_controller_parameters.to_tuple()),
        "before_home": before_home,
        "after_home": after_home,
        "after_power_cycle": after_power_cycle,
    }


def main() -> int:
    args = _parse_args()
    with HexMazeInterface(debug=args.debug) as hmi:
        hmi._validate_prism_address(args.prism)

        initial_verify = _power_cycle(hmi, args.cluster)
        initial_home = _initial_home(hmi, args.cluster, args)
        repeat_home = _repeat_home_test(hmi, args.cluster, args)
        command_during_home = _command_during_home_test(hmi, args.cluster, args)
        pause_resume = _pause_resume_test(hmi, args.cluster, args)
        queue_overflow = _queue_overflow_test(hmi, args.cluster, args)
        distributed_cluster_motion = _distributed_cluster_motion_test(hmi, args.cluster, args)
        parameter_persistence = _parameter_persistence_test(hmi, args.cluster, args)
        final_cleanup_home = _final_cleanup_home(hmi, args.cluster, args)

    print(
        json.dumps(
            {
                "cluster": args.cluster,
                "prism": args.prism,
                "initial_verify": initial_verify,
                "initial_home": initial_home,
                "repeat_home": repeat_home,
                "command_during_home": command_during_home,
                "pause_resume": pause_resume,
                "queue_overflow": queue_overflow,
                "distributed_cluster_motion": distributed_cluster_motion,
                "parameter_persistence": parameter_persistence,
                "final_cleanup_home": final_cleanup_home,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
