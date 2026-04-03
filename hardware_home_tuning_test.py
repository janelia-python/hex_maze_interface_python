#!/usr/bin/env python3
"""Sweep a small set of home parameters on live hardware."""

from __future__ import annotations

import argparse
import itertools
import json
import time

from hex_maze_interface import HexMazeInterface, HomeOutcome, HomeParameters, MazeException


def _parse_csv_ints(value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--travel-limits", type=_parse_csv_ints, default=(200, 250, 300))
    parser.add_argument("--max-velocities", type=_parse_csv_ints, default=(15, 20, 25))
    parser.add_argument("--run-currents", type=_parse_csv_ints, default=(45, 50, 55))
    parser.add_argument("--stall-thresholds", type=_parse_csv_ints, default=(8, 10, 12))
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
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
        if any(outcome == HomeOutcome.FAILED for outcome in last["outcomes"]):
            raise MazeException(
                f"cluster {cluster_address} reported failed home outcome: "
                f"{[outcome.name for outcome in last['outcomes']]}"
            )
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish homing: {last}")


def _profile_key(parameters: HomeParameters) -> list[int]:
    return list(parameters.to_tuple())


def main() -> int:
    args = _parse_args()
    pre_home_targets = (90, 100, 110, 120, 130, 140, 150)
    zero_targets = (0,) * 7
    profiles = [
        HomeParameters(
            travel_limit=travel_limit,
            max_velocity=max_velocity,
            run_current=run_current,
            stall_threshold=stall_threshold,
        )
        for travel_limit, max_velocity, run_current, stall_threshold in itertools.product(
            args.travel_limits,
            args.max_velocities,
            args.run_currents,
            args.stall_thresholds,
        )
    ]

    results: list[dict[str, object]] = []
    with HexMazeInterface(debug=args.debug) as hmi:
        for home_parameters in profiles:
            profile_result: dict[str, object] = {
                "home_parameters": _profile_key(home_parameters),
                "trials": [],
            }
            try:
                for _ in range(args.trials):
                    if not hmi.power_off_cluster(args.cluster):
                        raise MazeException("power_off_cluster failed")
                    if not hmi.power_on_cluster(args.cluster):
                        raise MazeException("power_on_cluster failed")
                    if not hmi.write_targets_cluster(args.cluster, pre_home_targets):
                        raise MazeException("write_targets_cluster failed before home")
                    staged_positions = _wait_for_positions(
                        hmi,
                        args.cluster,
                        pre_home_targets,
                        args.position_timeout,
                        args.poll_interval,
                        args.position_tolerance,
                    )
                    if not hmi.home_cluster(args.cluster, home_parameters):
                        raise MazeException("home_cluster failed to start")
                    home_report = _wait_for_home(
                        hmi,
                        args.cluster,
                        args.home_timeout,
                        args.poll_interval,
                    )
                    zero_positions = _wait_for_positions(
                        hmi,
                        args.cluster,
                        zero_targets,
                        args.position_timeout,
                        args.poll_interval,
                        args.position_tolerance,
                    )
                    if not all(home_report["homed"]):
                        raise MazeException(f"not fully homed: {home_report}")
                    profile_result["trials"].append(
                        {
                            "staged_positions_mm": list(staged_positions),
                            "home": home_report,
                            "zero_positions_mm": list(zero_positions),
                        }
                    )
                profile_result["ok"] = True
            except MazeException as exc:
                profile_result["ok"] = False
                profile_result["error"] = str(exc)
                try:
                    profile_result["positions_mm"] = list(hmi.read_positions_cluster(args.cluster))
                except MazeException:
                    pass
            results.append(profile_result)

    print(json.dumps({"cluster": args.cluster, "profiles": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
