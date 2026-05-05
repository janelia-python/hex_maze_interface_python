#!/usr/bin/env python3
"""Desk-rig hardware acceptance test for one live cluster."""

from __future__ import annotations

import argparse
import json
import time

from hex_maze_interface import HexMazeInterface, HomeOutcome, HomeParameters, MazeException


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--prism", type=int, default=0, help="Primary prism for per-prism tests.")
    parser.add_argument("--initial-travel-limit", type=int, default=700)
    parser.add_argument("--travel-limit", type=int, default=250)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--soak-iterations", type=int, default=50)
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


def _wait_for_home_completion(
    hmi: HexMazeInterface,
    cluster_address: int,
    expected_homed: tuple[bool, ...],
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    last = {
        "homed": tuple(bool(value) for value in hmi.homed_cluster(cluster_address)),
        "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
        "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
    }
    while time.monotonic() < deadline:
        last = {
            "homed": tuple(bool(value) for value in hmi.homed_cluster(cluster_address)),
            "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
            "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
        }
        if any(outcome == HomeOutcome.FAILED for outcome in last["outcomes"]):
            raise MazeException(
                f"cluster {cluster_address} reported failed home outcome: "
                f"{[outcome.name for outcome in last['outcomes']]}"
            )
        if last["homed"] == expected_homed:
            return {
                "homed": list(last["homed"]),
                "outcomes": [outcome.name for outcome in last["outcomes"]],
                "positions_mm": list(last["positions_mm"]),
            }
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} did not reach homed state {list(expected_homed)}; "
        f"last state was {last}"
    )


def _home_until_expected_homed(
    hmi: HexMazeInterface,
    cluster_address: int,
    home_parameters: HomeParameters,
    expected_homed: tuple[bool, ...],
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
        report = _wait_for_home_completion(
            hmi,
            cluster_address,
            expected_homed,
            timeout_s,
            poll_interval_s,
        )
        reports.append(report)
        if tuple(report["homed"]) == expected_homed:
            return reports
    raise MazeException(
        "cluster "
        f"{cluster_address} did not reach expected homed state "
        f"after {max_attempts} attempts: {reports[-1]}"
    )


def _wait_for_cluster_alive(
    hmi: HexMazeInterface,
    cluster_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    last_report: dict[str, object] = {"cluster_address": cluster_address, "ok": False, "checks": {}}
    while time.monotonic() < deadline:
        last_report = hmi.verify_cluster(cluster_address)
        if last_report.get("checks", {}).get("communicating", False):
            return last_report
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} did not resume communication; last report was {last_report}"
    )


def _assert_all_prisms_visible(positions_mm: tuple[int, ...]) -> None:
    missing = [index for index, position in enumerate(positions_mm) if position < 0]
    if missing:
        raise MazeException(
            f"non-communicating prisms reported positions < 0 at addresses {missing}"
        )


def _power_cycle_and_verify(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    if not hmi.power_off_cluster(cluster_address):
        raise MazeException("initial power_off_cluster failed")
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException("initial power_on_cluster failed")
    report = _wait_for_cluster_alive(hmi, cluster_address, args.home_timeout, args.poll_interval)
    _assert_all_prisms_visible(tuple(report["checks"]["positions_mm"]))
    return report


def _initial_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    home_parameters = HomeParameters(
        travel_limit=args.initial_travel_limit,
        max_velocity=20,
        run_current=50,
        stall_threshold=0,
    )
    return _home_until_expected_homed(
        hmi,
        cluster_address,
        home_parameters,
        (True,) * hmi.PRISM_COUNT,
        args.home_timeout,
        args.poll_interval,
        3,
    )


def _single_prism_home_isolation_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    prism_address = args.prism
    staged_targets = tuple(90 + 10 * index for index in range(hmi.PRISM_COUNT))
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=20,
        run_current=50,
        stall_threshold=0,
    )

    if not hmi.write_targets_cluster(cluster_address, staged_targets):
        raise MazeException("single-prism-home-isolation: write_targets_cluster failed")
    staged_positions = _wait_for_positions(
        hmi,
        cluster_address,
        staged_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    if not hmi.home_prism(cluster_address, prism_address, home_parameters):
        raise MazeException("single-prism-home-isolation: home_prism failed")
    deadline = time.monotonic() + args.home_timeout
    home_report: dict[str, object] | None = None
    while time.monotonic() < deadline:
        outcomes = tuple(hmi.read_home_outcomes_cluster(cluster_address))
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        homed = tuple(bool(value) for value in hmi.homed_cluster(cluster_address))
        if outcomes[prism_address] != HomeOutcome.IN_PROGRESS:
            home_report = {
                "homed": list(homed),
                "outcomes": [outcome.name for outcome in outcomes],
                "positions_mm": list(positions),
            }
            break
        if any(outcome == HomeOutcome.FAILED for outcome in outcomes):
            raise MazeException(
                "single-prism-home-isolation: "
                f"failed home outcome {[outcome.name for outcome in outcomes]}"
            )
        time.sleep(args.poll_interval)
    if home_report is None:
        raise MazeException("single-prism-home-isolation: prism home did not complete in time")

    final_positions = tuple(home_report["positions_mm"])
    if abs(final_positions[prism_address]) > args.position_tolerance:
        raise MazeException(
            "single-prism-home-isolation: homed prism did not settle near zero; "
            f"position was {final_positions[prism_address]}"
        )
    untouched_positions = [
        position for index, position in enumerate(final_positions) if index != prism_address
    ]
    untouched_targets = [
        target for index, target in enumerate(staged_targets) if index != prism_address
    ]
    if any(
        abs(position - target) > args.position_tolerance
        for position, target in zip(untouched_positions, untouched_targets, strict=True)
    ):
        raise MazeException(
            "single-prism-home-isolation: non-addressed prisms moved unexpectedly; "
            f"positions were {list(final_positions)}"
        )

    return {
        "prism_address": prism_address,
        "staged_targets_mm": list(staged_targets),
        "staged_positions_mm": list(staged_positions),
        "home": home_report,
    }


def _cluster_pause_resume_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=20,
        run_current=50,
        stall_threshold=0,
    )
    initial_targets = tuple(40 + 10 * index for index in range(hmi.PRISM_COUNT))
    queued_single_target = 185
    queued_cluster_targets = tuple(120 + 5 * index for index in range(hmi.PRISM_COUNT))

    # Restore a known all-homed baseline so this test does not depend on the
    # mixed post-state left behind by single-prism isolation.
    home_report = _home_until_expected_homed(
        hmi,
        cluster_address,
        home_parameters,
        (True,) * hmi.PRISM_COUNT,
        args.home_timeout,
        args.poll_interval,
        2,
    )

    if not hmi.write_targets_cluster(cluster_address, initial_targets):
        raise MazeException("cluster-pause-resume: failed to stage initial targets")
    initial_positions = _wait_for_positions(
        hmi,
        cluster_address,
        initial_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    if not hmi.pause_cluster(cluster_address):
        raise MazeException("cluster-pause-resume: pause_cluster failed")

    if not hmi.write_target_prism(cluster_address, args.prism, queued_single_target):
        raise MazeException("cluster-pause-resume: write_target_prism while paused failed")
    if not hmi.write_targets_cluster(cluster_address, queued_cluster_targets):
        raise MazeException("cluster-pause-resume: write_targets_cluster while paused failed")

    paused_before = tuple(hmi.read_positions_cluster(cluster_address))
    time.sleep(0.75)
    paused_after = tuple(hmi.read_positions_cluster(cluster_address))
    if any(
        abs(after - before) > args.position_tolerance
        for before, after in zip(paused_before, paused_after, strict=True)
    ):
        raise MazeException(
            "cluster-pause-resume: positions changed while paused; "
            f"before={list(paused_before)} after={list(paused_after)}"
        )

    if not hmi.resume_cluster(cluster_address):
        raise MazeException("cluster-pause-resume: resume_cluster failed")
    final_positions = _wait_for_positions(
        hmi,
        cluster_address,
        queued_cluster_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    return {
        "home": home_report,
        "initial_targets_mm": list(initial_targets),
        "initial_positions_mm": list(initial_positions),
        "queued_single_target_mm": queued_single_target,
        "queued_cluster_targets_mm": list(queued_cluster_targets),
        "paused_positions_before_mm": list(paused_before),
        "paused_positions_after_mm": list(paused_after),
        "final_positions_mm": list(final_positions),
    }


def _reset_recovery_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    move_targets = tuple(70 + 15 * index for index in range(hmi.PRISM_COUNT))
    recovery_targets = tuple(30 + 5 * index for index in range(hmi.PRISM_COUNT))

    if not hmi.write_targets_cluster(cluster_address, move_targets):
        raise MazeException("reset-recovery: write_targets_cluster failed")
    moved_positions = _wait_for_positions(
        hmi,
        cluster_address,
        move_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    if not hmi.reset_cluster(cluster_address):
        raise MazeException("reset-recovery: reset_cluster failed")
    verify_after_reset = _wait_for_cluster_alive(
        hmi,
        cluster_address,
        args.home_timeout,
        args.poll_interval,
    )
    reset_positions = tuple(verify_after_reset["checks"]["positions_mm"])
    if any(position >= 0 for position in reset_positions):
        raise MazeException(
            "reset-recovery: expected reset_cluster to leave prisms powered off; "
            f"got positions {list(reset_positions)}"
        )

    if not hmi.power_on_cluster(cluster_address):
        raise MazeException("reset-recovery: power_on_cluster after reset failed")
    verify_after_power_on = _wait_for_cluster_alive(
        hmi,
        cluster_address,
        args.home_timeout,
        args.poll_interval,
    )
    _assert_all_prisms_visible(tuple(verify_after_power_on["checks"]["positions_mm"]))

    if not hmi.write_targets_cluster(cluster_address, recovery_targets):
        raise MazeException("reset-recovery: write_targets_cluster after reset failed")
    recovered_positions = _wait_for_positions(
        hmi,
        cluster_address,
        recovery_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    return {
        "move_targets_mm": list(move_targets),
        "moved_positions_mm": list(moved_positions),
        "verify_after_reset": verify_after_reset,
        "verify_after_power_on": verify_after_power_on,
        "recovery_targets_mm": list(recovery_targets),
        "recovered_positions_mm": list(recovered_positions),
    }


def _command_idempotence_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    prism_address = args.prism
    repeated_target = 135
    repeat_count = 3

    for _ in range(repeat_count):
        if not hmi.write_target_prism(cluster_address, prism_address, repeated_target):
            raise MazeException("command-idempotence: write_target_prism failed")
    final_position = _wait_for_prism_position(
        hmi,
        cluster_address,
        prism_address,
        repeated_target,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    return {
        "prism_address": prism_address,
        "repeated_target_mm": repeated_target,
        "repeat_count": repeat_count,
        "final_position_mm": final_position,
    }


def _communication_soak_test(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    max_latency_s = 0.0

    for _ in range(args.soak_iterations):
        started = time.monotonic()
        verify_report = hmi.verify_cluster(cluster_address)
        latency_s = time.monotonic() - started
        max_latency_s = max(max_latency_s, latency_s)
        if not verify_report.get("checks", {}).get("communicating", False):
            raise MazeException(
                f"communication-soak: communication failed during verify report {verify_report}"
            )
        positions = tuple(verify_report["checks"]["positions_mm"])
        _assert_all_prisms_visible(positions)
        samples.append(
            {
                "latency_ms": round(latency_s * 1000, 3),
                "positions_mm": list(positions),
                "homed": list(verify_report["checks"]["homed"]),
            }
        )
        time.sleep(min(args.poll_interval, 0.1))

    return {
        "iterations": args.soak_iterations,
        "max_latency_ms": round(max_latency_s * 1000, 3),
        "samples": samples,
    }


def main() -> int:
    args = _parse_args()
    with HexMazeInterface(debug=args.debug) as hmi:
        hmi._validate_prism_address(args.prism)

        initial_verify = _power_cycle_and_verify(hmi, args.cluster, args)
        initial_home = _initial_home(hmi, args.cluster, args)
        single_prism_home_isolation = _single_prism_home_isolation_test(hmi, args.cluster, args)
        cluster_pause_resume = _cluster_pause_resume_test(hmi, args.cluster, args)
        reset_recovery = _reset_recovery_test(hmi, args.cluster, args)
        command_idempotence = _command_idempotence_test(hmi, args.cluster, args)
        communication_soak = _communication_soak_test(hmi, args.cluster, args)

    print(
        json.dumps(
            {
                "cluster": args.cluster,
                "prism": args.prism,
                "initial_verify": initial_verify,
                "initial_home": initial_home,
                "single_prism_home_isolation": single_prism_home_isolation,
                "cluster_pause_resume": cluster_pause_resume,
                "reset_recovery": reset_recovery,
                "command_idempotence": command_idempotence,
                "communication_soak": communication_soak,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
