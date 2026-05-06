#!/usr/bin/env python3
"""Minimal hardware smoke test for one or more live clusters."""

from __future__ import annotations

import argparse
import json
import random
import time

from hex_maze_interface import HexMazeInterface, HomeOutcome, HomeParameters, MazeException


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=int, nargs="+", required=True)
    parser.add_argument("--initial-travel-limit", type=int, default=100)
    parser.add_argument("--travel-limit", type=int, default=100)
    parser.add_argument("--initial-home-attempts", type=int, default=7)
    parser.add_argument("--max-velocity", type=int, default=6)
    parser.add_argument("--run-current", type=int, default=43)
    parser.add_argument("--stall-threshold", type=int, default=0)
    parser.add_argument("--move", type=int, default=40, help="Positive post-home target in mm.")
    parser.add_argument(
        "--pre-home-low",
        type=int,
        default=40,
        help="Lower bound for initial interior pre-home positions in mm.",
    )
    parser.add_argument(
        "--pre-home-high",
        type=int,
        default=160,
        help="Upper bound for initial interior pre-home positions in mm.",
    )
    parser.add_argument(
        "--position-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for commanded moves to settle.",
    )
    parser.add_argument(
        "--position-tolerance",
        type=int,
        default=5,
        help="Allowed absolute error in mm when checking settled positions.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=10,
        help="Random seed for reproducible pre-home positions.",
    )
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--home-timeout", type=float, default=30.0)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _wait_for_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        homed = tuple(hmi.homed_cluster(cluster_address))
        outcomes = tuple(hmi.read_home_outcomes_cluster(cluster_address))
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        if all(outcome != HomeOutcome.IN_PROGRESS for outcome in outcomes):
            return {
                "homed": homed,
                "outcomes": [outcome.name for outcome in outcomes],
                "positions_mm": positions,
            }
        if any(outcome == HomeOutcome.FAILED for outcome in outcomes):
            raise MazeException(
                f"cluster {cluster_address} reported failed home outcome: "
                f"{[outcome.name for outcome in outcomes]}"
            )
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish homing within {timeout_s:.1f}s")


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


def _wait_for_positions(
    hmi: HexMazeInterface,
    cluster_address: int,
    targets_mm: tuple[int, ...],
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
) -> tuple[int, ...]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        if all(
            abs(position - target) <= tolerance_mm
            for position, target in zip(positions, targets_mm, strict=True)
        ):
            return positions
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} did not reach targets {list(targets_mm)} "
        f"within {timeout_s:.1f}s"
    )


def _run_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
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
    if args.pre_home_low >= args.pre_home_high:
        raise MazeException("--pre-home-low must be less than --pre-home-high")

    rng = random.Random(args.seed + cluster_address)
    pre_home_targets = tuple(
        rng.randint(args.pre_home_low, args.pre_home_high) for _ in range(hmi.PRISM_COUNT)
    )
    move_targets = (args.move,) * hmi.PRISM_COUNT
    zero_targets = (0,) * hmi.PRISM_COUNT

    if not hmi.verify_cluster(cluster_address)["checks"].get("communicating", False):
        raise MazeException(f"cluster {cluster_address} failed communication check")
    if not hmi.power_off_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} failed power-off")
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} failed power-on")
    initial_home_report = _home_until_all_homed(
        hmi,
        cluster_address,
        initial_home_parameters,
        args.home_timeout,
        args.poll_interval,
        args.initial_home_attempts,
    )
    for prism_address, target_mm in enumerate(pre_home_targets):
        if not hmi.write_target_prism(cluster_address, prism_address, target_mm):
            raise MazeException(
                f"cluster {cluster_address} failed pre-home move for prism {prism_address}"
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

    if not hmi.write_targets_cluster(cluster_address, move_targets):
        raise MazeException(f"cluster {cluster_address} failed positive move command")
    moved_positions = _wait_for_positions(
        hmi,
        cluster_address,
        move_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    if not hmi.write_targets_cluster(cluster_address, zero_targets):
        raise MazeException(f"cluster {cluster_address} failed return-to-zero command")
    zero_positions = _wait_for_positions(
        hmi,
        cluster_address,
        zero_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )

    return {
        "cluster_address": cluster_address,
        "pre_home_targets_mm": pre_home_targets,
        "pre_home_positions_mm": pre_home_positions,
        "verify": hmi.verify_cluster(cluster_address),
        "initial_home": initial_home_report,
        "home": home_report,
        "moved_positions_mm": moved_positions,
        "zero_positions_mm": zero_positions,
    }


def main() -> int:
    args = _parse_args()
    results: list[dict[str, object]] = []
    with HexMazeInterface(debug=args.debug) as hmi:
        for cluster_address in args.clusters:
            results.append(_run_cluster(hmi, cluster_address, args))
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
