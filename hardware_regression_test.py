#!/usr/bin/env python3
"""Single-cluster hardware regression test for repeated homing and motion."""

from __future__ import annotations

import argparse
import json
import random
import time

from hex_maze_interface import HexMazeInterface, HomeOutcome, HomeParameters, MazeException


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--initial-travel-limit", type=int, default=700)
    parser.add_argument("--travel-limit", type=int, default=400)
    parser.add_argument("--initial-home-attempts", type=int, default=3)
    parser.add_argument("--max-velocity", type=int, default=20)
    parser.add_argument("--run-current", type=int, default=50)
    parser.add_argument("--stall-threshold", type=int, default=0)
    parser.add_argument("--pre-home-low", type=int, default=80)
    parser.add_argument("--pre-home-high", type=int, default=160)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
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


def _ensure_cluster_is_alive(hmi: HexMazeInterface, cluster_address: int) -> None:
    if not hmi.communicating_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} stopped communicating")


def _random_targets(rng: random.Random, low: int, high: int, count: int) -> tuple[int, ...]:
    return tuple(rng.randint(low, high) for _ in range(count))


def _run_cycle(
    hmi: HexMazeInterface,
    cluster_address: int,
    cycle_index: int,
    args: argparse.Namespace,
    rng: random.Random,
) -> dict[str, object]:
    initial_home_parameters = HomeParameters(
        travel_limit=args.initial_travel_limit,
        max_velocity=args.max_velocity,
        run_current=args.run_current,
        stall_threshold=args.stall_threshold,
    )
    home_parameters = HomeParameters(
        travel_limit=args.travel_limit,
        max_velocity=args.max_velocity,
        run_current=args.run_current,
        stall_threshold=args.stall_threshold,
    )

    pre_home_targets = _random_targets(rng, args.pre_home_low, args.pre_home_high, hmi.PRISM_COUNT)
    single_prism_targets = _random_targets(
        rng, args.pre_home_low // 2, args.pre_home_high - 20, hmi.PRISM_COUNT
    )
    cluster_targets = _random_targets(
        rng, args.pre_home_low // 2, args.pre_home_high - 20, hmi.PRISM_COUNT
    )
    double_prism_targets = (
        rng.randint(args.pre_home_low // 2, args.pre_home_high - 40),
        rng.randint(args.pre_home_low // 2, args.pre_home_high - 20),
    )
    double_cluster_targets = tuple(
        (
            rng.randint(args.pre_home_low // 2, args.pre_home_high - 40),
            rng.randint(args.pre_home_low // 2, args.pre_home_high - 20),
        )
        for _ in range(hmi.PRISM_COUNT)
    )

    if not hmi.power_off_cluster(cluster_address):
        raise MazeException(f"cycle {cycle_index}: power_off_cluster failed")
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException(f"cycle {cycle_index}: power_on_cluster failed")
    initial_home_report = _home_until_all_homed(
        hmi,
        cluster_address,
        initial_home_parameters,
        args.home_timeout,
        args.poll_interval,
        args.initial_home_attempts,
    )
    if any(outcome != HomeOutcome.STALL.name for outcome in initial_home_report[-1]["outcomes"]):
        raise MazeException(
            "cycle "
            f"{cycle_index}: expected all STALL outcomes after initial home, "
            f"got {initial_home_report[-1]['outcomes']}"
        )

    for prism_address, target_mm in enumerate(pre_home_targets):
        if not hmi.write_target_prism(cluster_address, prism_address, target_mm):
            raise MazeException(
                f"cycle {cycle_index}: write_target_prism failed for prism {prism_address}"
            )
    pre_home_positions = _wait_for_positions(
        hmi,
        cluster_address,
        pre_home_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    home_report = _home_until_all_homed(
        hmi,
        cluster_address,
        home_parameters,
        args.home_timeout,
        args.poll_interval,
        2,
    )
    if any(outcome != HomeOutcome.STALL.name for outcome in home_report[-1]["outcomes"]):
        raise MazeException(
            f"cycle {cycle_index}: expected all STALL outcomes, got {home_report[-1]['outcomes']}"
        )

    for prism_address, target_mm in enumerate(single_prism_targets):
        if not hmi.write_target_prism(cluster_address, prism_address, target_mm):
            raise MazeException(
                f"cycle {cycle_index}: write_target_prism failed for prism {prism_address}"
            )
    single_prism_positions = _wait_for_positions(
        hmi,
        cluster_address,
        single_prism_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    _ensure_cluster_is_alive(hmi, cluster_address)

    if not hmi.write_targets_cluster(cluster_address, cluster_targets):
        raise MazeException(f"cycle {cycle_index}: write_targets_cluster failed")
    cluster_positions = _wait_for_positions(
        hmi,
        cluster_address,
        cluster_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    _ensure_cluster_is_alive(hmi, cluster_address)

    prism_address = cycle_index % hmi.PRISM_COUNT
    if not hmi.write_double_target_prism(cluster_address, prism_address, double_prism_targets):
        raise MazeException(
            f"cycle {cycle_index}: write_double_target_prism failed for prism {prism_address}"
        )
    expected_after_double_prism = list(cluster_targets)
    expected_after_double_prism[prism_address] = double_prism_targets[1]
    double_prism_positions = _wait_for_positions(
        hmi,
        cluster_address,
        tuple(expected_after_double_prism),
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    _ensure_cluster_is_alive(hmi, cluster_address)

    if not hmi.write_double_targets_cluster(cluster_address, double_cluster_targets):
        raise MazeException(f"cycle {cycle_index}: write_double_targets_cluster failed")
    expected_after_double_cluster = tuple(pair[1] for pair in double_cluster_targets)
    double_cluster_positions = _wait_for_positions(
        hmi,
        cluster_address,
        expected_after_double_cluster,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    _ensure_cluster_is_alive(hmi, cluster_address)

    return {
        "cycle": cycle_index,
        "initial_home": initial_home_report,
        "pre_home_targets_mm": list(pre_home_targets),
        "pre_home_positions_mm": list(pre_home_positions),
        "home": home_report,
        "single_prism_targets_mm": list(single_prism_targets),
        "single_prism_positions_mm": list(single_prism_positions),
        "cluster_targets_mm": list(cluster_targets),
        "cluster_positions_mm": list(cluster_positions),
        "double_prism_address": prism_address,
        "double_prism_targets_mm": list(double_prism_targets),
        "double_prism_positions_mm": list(double_prism_positions),
        "double_cluster_targets_mm": [list(pair) for pair in double_cluster_targets],
        "double_cluster_positions_mm": list(double_cluster_positions),
    }


def main() -> int:
    args = _parse_args()
    rng = random.Random(args.seed + args.cluster)
    with HexMazeInterface(debug=args.debug) as hmi:
        _ensure_cluster_is_alive(hmi, args.cluster)
        results = [
            _run_cycle(hmi, args.cluster, cycle_index, args, rng)
            for cycle_index in range(args.cycles)
        ]
    print(json.dumps({"cluster": args.cluster, "cycles": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
