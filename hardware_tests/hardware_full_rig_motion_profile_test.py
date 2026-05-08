#!/usr/bin/env python3
"""Run one full-rig motion profile and park all prisms at a visual check height."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from hex_maze_interface import ControllerParameters, HexMazeInterface, MazeException


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-name", default="custom")
    parser.add_argument(
        "--clusters", type=int, nargs="+", default=HexMazeInterface.CLUSTER_ADDRESSES
    )
    parser.add_argument("--start-velocity", type=int, default=10)
    parser.add_argument("--stop-velocity", type=int, default=10)
    parser.add_argument("--first-velocity", type=int, default=50)
    parser.add_argument("--max-velocity", type=int, default=50)
    parser.add_argument("--first-acceleration", type=int, default=120)
    parser.add_argument("--max-acceleration", type=int, default=80)
    parser.add_argument("--max-deceleration", type=int, default=80)
    parser.add_argument("--first-deceleration", type=int, default=120)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--low", type=int, default=40)
    parser.add_argument("--high", type=int, default=340)
    parser.add_argument("--check-height", type=int, default=200)
    parser.add_argument("--position-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.10)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--settle-s", type=float, default=0.25)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _controller_parameters(args: argparse.Namespace) -> ControllerParameters:
    return ControllerParameters(
        start_velocity=args.start_velocity,
        stop_velocity=args.stop_velocity,
        first_velocity=args.first_velocity,
        max_velocity=args.max_velocity,
        first_acceleration=args.first_acceleration,
        max_acceleration=args.max_acceleration,
        max_deceleration=args.max_deceleration,
        first_deceleration=args.first_deceleration,
    )


def _targets_for_pattern(
    cluster_index: int,
    cycle_index: int,
    pattern_index: int,
    low: int,
    high: int,
) -> tuple[int, ...]:
    span = high - low
    if span < 0:
        raise MazeException(f"invalid target range: low={low}, high={high}")
    values = []
    for prism_index in range(HexMazeInterface.PRISM_COUNT):
        raw = (cycle_index * 53 + pattern_index * 97 + cluster_index * 41 + prism_index * 37) % (
            span + 1
        )
        if pattern_index % 2:
            raw = span - raw
        values.append(low + raw)
    return tuple(values)


def _common_targets(position_mm: int) -> tuple[int, ...]:
    return (position_mm,) * HexMazeInterface.PRISM_COUNT


def _positions_match(
    positions: tuple[int, ...],
    targets: tuple[int, ...],
    tolerance_mm: int,
) -> bool:
    return all(
        abs(position - target) <= tolerance_mm for position, target in zip(positions, targets)
    )


def _wait_for_all_targets(
    hmi: HexMazeInterface,
    targets_by_cluster: dict[int, tuple[int, ...]],
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
) -> tuple[dict[int, tuple[int, ...]], float]:
    started = time.monotonic()
    deadline = started + timeout_s
    last_positions: dict[int, tuple[int, ...]] = {}
    while time.monotonic() < deadline:
        last_positions = {
            cluster: tuple(hmi.read_positions_cluster(cluster)) for cluster in targets_by_cluster
        }
        if all(
            _positions_match(last_positions[cluster], targets, tolerance_mm)
            for cluster, targets in targets_by_cluster.items()
        ):
            return last_positions, time.monotonic() - started
        time.sleep(poll_interval_s)
    raise MazeException(
        "timed out waiting for targets: "
        + json.dumps(
            {
                cluster: {
                    "target": list(targets_by_cluster[cluster]),
                    "last": list(positions),
                }
                for cluster, positions in last_positions.items()
            },
            sort_keys=True,
        )
    )


def _move_all_clusters(
    hmi: HexMazeInterface,
    targets_by_cluster: dict[int, tuple[int, ...]],
    args: argparse.Namespace,
) -> dict[str, object]:
    command_started = time.monotonic()
    writes = {
        cluster: hmi.write_targets_cluster(cluster, targets)
        for cluster, targets in targets_by_cluster.items()
    }
    command_time_s = time.monotonic() - command_started
    if not all(writes.values()):
        raise MazeException(f"write_targets_cluster failed: {writes}")
    final_positions, wait_time_s = _wait_for_all_targets(
        hmi,
        targets_by_cluster,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    time.sleep(args.settle_s)
    return {
        "command_time_s": round(command_time_s, 3),
        "wait_time_s": round(wait_time_s, 3),
        "targets_mm": {
            str(cluster): list(targets) for cluster, targets in targets_by_cluster.items()
        },
        "final_positions_mm": {
            str(cluster): list(positions) for cluster, positions in final_positions.items()
        },
    }


def main() -> int:
    args = _parse_args()
    clusters = tuple(args.clusters)
    controller_parameters = _controller_parameters(args)

    with HexMazeInterface(debug=args.debug) as hmi:
        clear_diagnostics = hmi.clear_prism_diagnostics_all_clusters()
        controller_write = hmi.write_controller_parameters_all_clusters(controller_parameters)
        if not all(controller_write):
            raise MazeException(
                f"write_controller_parameters_all_clusters failed: {controller_write}"
            )
        readback = {
            cluster: asdict(hmi.read_controller_parameters_cluster(cluster)) for cluster in clusters
        }

        moves: list[dict[str, object]] = []
        for cycle_index in range(args.cycles):
            for pattern_index in range(2):
                targets_by_cluster = {
                    cluster: _targets_for_pattern(
                        cluster_index,
                        cycle_index,
                        pattern_index,
                        args.low,
                        args.high,
                    )
                    for cluster_index, cluster in enumerate(clusters)
                }
                move_report = _move_all_clusters(hmi, targets_by_cluster, args)
                move_report["cycle"] = cycle_index + 1
                move_report["pattern"] = pattern_index + 1
                moves.append(move_report)

        check_targets = {cluster: _common_targets(args.check_height) for cluster in clusters}
        check_report = _move_all_clusters(hmi, check_targets, args)
        diagnostics = {
            str(cluster): [
                asdict(diagnostic) for diagnostic in hmi.read_prism_diagnostics_cluster(cluster)
            ]
            for cluster in clusters
        }

    print(
        json.dumps(
            {
                "profile_name": args.profile_name,
                "clusters": list(clusters),
                "controller_parameters": asdict(controller_parameters),
                "controller_write": controller_write,
                "controller_readback": readback,
                "clear_diagnostics": clear_diagnostics,
                "cycles": args.cycles,
                "target_range_mm": [args.low, args.high],
                "visual_check_height_mm": args.check_height,
                "moves": moves,
                "visual_check": check_report,
                "diagnostics": diagnostics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
