#!/usr/bin/env python3
"""Bench-tune controller parameters for fast but reliable cluster moves."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--home-travel-limit", type=int, default=250)
    parser.add_argument("--home-max-velocity", type=int, default=20)
    parser.add_argument("--home-run-current", type=int, default=50)
    parser.add_argument("--home-stall-threshold", type=int, default=0)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _wait_for_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    last = {
        "homed": tuple(bool(v) for v in hmi.homed_cluster(cluster_address)),
        "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
        "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
    }
    while time.monotonic() < deadline:
        last = {
            "homed": tuple(bool(v) for v in hmi.homed_cluster(cluster_address)),
            "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
            "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
        }
        if all(outcome != HomeOutcome.IN_PROGRESS for outcome in last["outcomes"]):
            return {
                "homed": list(last["homed"]),
                "outcomes": [outcome.name for outcome in last["outcomes"]],
                "positions_mm": list(last["positions_mm"]),
            }
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish homing: {last}")


def _wait_for_positions(
    hmi: HexMazeInterface,
    cluster_address: int,
    targets_mm: tuple[int, ...],
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
) -> tuple[tuple[int, ...], float]:
    started = time.monotonic()
    deadline = started + timeout_s
    last_positions = tuple(hmi.read_positions_cluster(cluster_address))
    while time.monotonic() < deadline:
        last_positions = tuple(hmi.read_positions_cluster(cluster_address))
        if all(
            abs(position - target) <= tolerance_mm
            for position, target in zip(last_positions, targets_mm, strict=True)
        ):
            return last_positions, time.monotonic() - started
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} did not reach targets {list(targets_mm)}; "
        f"last positions were {list(last_positions)}"
    )


def _profile_candidates() -> list[tuple[str, ControllerParameters]]:
    # Keep the GUI's more aggressive mid-ramp tuning and sweep only the
    # low-speed ramp entry/exit values that were found to be sensitive.
    base = dict(
        first_velocity=40,
        max_velocity=40,
        first_acceleration=120,
        max_acceleration=80,
        max_deceleration=80,
        first_deceleration=120,
    )
    return [
        ("bench_baseline", ControllerParameters(1, 5, 10, 20, 40, 20, 30, 50)),
        ("gui_safe_low", ControllerParameters(1, 5, **base)),
        ("gui_start_2_stop_5", ControllerParameters(2, 5, **base)),
        ("gui_start_3_stop_6", ControllerParameters(3, 6, **base)),
        ("gui_start_5_stop_5", ControllerParameters(5, 5, **base)),
        ("gui_start_5_stop_10", ControllerParameters(5, 10, **base)),
        ("gui_start_8_stop_8", ControllerParameters(8, 8, **base)),
        ("gui_start_10_stop_10", ControllerParameters(10, 10, **base)),
        ("gui_full", ControllerParameters(20, 20, **base)),
    ]


def main() -> int:
    args = _parse_args()
    move_targets = (90, 100, 110, 120, 130, 140, 150)
    zero_targets = (0,) * 7
    home_parameters = HomeParameters(
        travel_limit=args.home_travel_limit,
        max_velocity=args.home_max_velocity,
        run_current=args.home_run_current,
        stall_threshold=args.home_stall_threshold,
    )

    results: list[dict[str, object]] = []
    with HexMazeInterface(debug=args.debug) as hmi:
        if not hmi.power_off_cluster(args.cluster):
            raise MazeException("power_off_cluster failed")
        if not hmi.power_on_cluster(args.cluster):
            raise MazeException("power_on_cluster failed")
        if not hmi.home_cluster(args.cluster, home_parameters):
            raise MazeException("home_cluster failed to start")
        home_report = _wait_for_home(hmi, args.cluster, 25.0, args.poll_interval)
        if not all(home_report["homed"]):
            raise MazeException(f"home failed: {home_report}")

        for name, parameters in _profile_candidates():
            entry: dict[str, object] = {"profile": name, "parameters": list(parameters.to_tuple())}
            try:
                if not hmi.write_controller_parameters_cluster(args.cluster, parameters):
                    raise MazeException("write_controller_parameters_cluster failed")
                actual = hmi.read_controller_parameters_cluster(args.cluster).to_tuple()
                entry["readback"] = list(actual)

                zero_positions, zero_time_s = _wait_for_positions(
                    hmi,
                    args.cluster,
                    zero_targets,
                    args.position_timeout,
                    args.poll_interval,
                    args.position_tolerance,
                )
                entry["zero_positions_mm"] = list(zero_positions)
                entry["zero_time_s"] = round(zero_time_s, 3)

                if not hmi.write_targets_cluster(args.cluster, move_targets):
                    raise MazeException("write_targets_cluster failed")
                final_positions, move_time_s = _wait_for_positions(
                    hmi,
                    args.cluster,
                    move_targets,
                    args.position_timeout,
                    args.poll_interval,
                    args.position_tolerance,
                )
                entry["move_positions_mm"] = list(final_positions)
                entry["move_time_s"] = round(move_time_s, 3)

                if not hmi.write_targets_cluster(args.cluster, zero_targets):
                    raise MazeException("write_targets_cluster return-to-zero failed")
                return_positions, return_time_s = _wait_for_positions(
                    hmi,
                    args.cluster,
                    zero_targets,
                    args.position_timeout,
                    args.poll_interval,
                    args.position_tolerance,
                )
                entry["return_positions_mm"] = list(return_positions)
                entry["return_time_s"] = round(return_time_s, 3)
                entry["ok"] = True
            except MazeException as exc:
                entry["ok"] = False
                entry["error"] = str(exc)
                try:
                    entry["positions_mm"] = list(hmi.read_positions_cluster(args.cluster))
                except MazeException:
                    pass
            results.append(entry)

    print(
        json.dumps(
            {
                "cluster": args.cluster,
                "home": home_report,
                "move_targets_mm": list(move_targets),
                "profiles": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
