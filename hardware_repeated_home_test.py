#!/usr/bin/env python3
"""Regression test for repeated cluster homing followed by the first move."""

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
    parser.add_argument("--trial-count", type=int, default=10)
    parser.add_argument("--home-repeat-count", type=int, default=5)
    parser.add_argument("--home-travel-limit", type=int, default=250)
    parser.add_argument("--home-max-velocity", type=int, default=20)
    parser.add_argument("--home-run-current", type=int, default=50)
    parser.add_argument("--home-stall-threshold", type=int, default=10)
    parser.add_argument("--start-velocity", type=int, default=10)
    parser.add_argument("--stop-velocity", type=int, default=10)
    parser.add_argument("--first-velocity", type=int, default=40)
    parser.add_argument("--max-velocity", type=int, default=40)
    parser.add_argument("--first-acceleration", type=int, default=120)
    parser.add_argument("--max-acceleration", type=int, default=80)
    parser.add_argument("--max-deceleration", type=int, default=80)
    parser.add_argument("--first-deceleration", type=int, default=120)
    parser.add_argument("--move-target-base", type=int, default=40)
    parser.add_argument("--move-target-step", type=int, default=10)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
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


def _home_parameters(args: argparse.Namespace) -> HomeParameters:
    return HomeParameters(
        travel_limit=args.home_travel_limit,
        max_velocity=args.home_max_velocity,
        run_current=args.home_run_current,
        stall_threshold=args.home_stall_threshold,
    )


def _move_targets(args: argparse.Namespace) -> tuple[int, ...]:
    return tuple(
        args.move_target_base + args.move_target_step * prism_index
        for prism_index in range(HexMazeInterface.PRISM_COUNT)
    )


def _run_trial(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    if not hmi.power_off_cluster(cluster_address):
        raise MazeException("power_off_cluster failed")
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException("power_on_cluster failed")

    controller_parameters = _controller_parameters(args)
    if not hmi.write_controller_parameters_cluster(cluster_address, controller_parameters):
        raise MazeException("write_controller_parameters_cluster failed")

    home_reports: list[dict[str, object]] = []
    home_parameters = _home_parameters(args)
    for _ in range(args.home_repeat_count):
        if not hmi.home_cluster(cluster_address, home_parameters):
            raise MazeException("home_cluster failed to start")
        home_reports.append(
            _wait_for_home(hmi, cluster_address, args.home_timeout, args.poll_interval)
        )

    final_home = home_reports[-1]
    homed_flags = tuple(bool(value) for value in final_home["homed"])
    home_outcomes = tuple(str(value) for value in final_home["outcomes"])
    home_positions = tuple(int(value) for value in final_home["positions_mm"])
    inconsistent_homed_prisms = [
        prism_index
        for prism_index, (homed, outcome, position_mm) in enumerate(
            zip(homed_flags, home_outcomes, home_positions, strict=True)
        )
        if (not homed)
        and outcome == HomeOutcome.STALL.name
        and abs(position_mm) <= args.position_tolerance
    ]
    if not all(homed_flags) and len(inconsistent_homed_prisms) != len(
        [flag for flag in homed_flags if not flag]
    ):
        raise MazeException(f"not all prisms were homed after repeated home passes: {final_home}")

    targets_mm = _move_targets(args)
    before_move_positions = tuple(hmi.read_positions_cluster(cluster_address))
    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        raise MazeException("write_targets_cluster failed")

    try:
        final_positions = _wait_for_positions(
            hmi,
            cluster_address,
            targets_mm,
            args.position_timeout,
            args.poll_interval,
            args.position_tolerance,
        )
    except MazeException as exc:
        stalled_positions = tuple(hmi.read_positions_cluster(cluster_address))
        stationary_prisms = [
            prism_index
            for prism_index, (before_mm, after_mm) in enumerate(
                zip(before_move_positions, stalled_positions, strict=True)
            )
            if abs(after_mm - before_mm) <= args.position_tolerance
        ]
        raise MazeException(
            "first post-home move failed; "
            f"stationary_prisms={stationary_prisms}, "
            f"before_move_positions_mm={list(before_move_positions)}, "
            f"after_move_positions_mm={list(stalled_positions)}, "
            f"targets_mm={list(targets_mm)}"
        ) from exc

    stationary_prisms = [
        prism_index
        for prism_index, (before_mm, after_mm) in enumerate(
            zip(before_move_positions, final_positions, strict=True)
        )
        if abs(after_mm - before_mm) <= args.position_tolerance
    ]
    if stationary_prisms:
        raise MazeException(
            "one or more prisms never launched after repeated homing; "
            f"stationary_prisms={stationary_prisms}, "
            f"before_move_positions_mm={list(before_move_positions)}, "
            f"after_move_positions_mm={list(final_positions)}, "
            f"targets_mm={list(targets_mm)}"
        )

    return {
        "home_reports": home_reports,
        "inconsistent_homed_prisms": inconsistent_homed_prisms,
        "before_move_positions_mm": list(before_move_positions),
        "targets_mm": list(targets_mm),
        "final_positions_mm": list(final_positions),
    }


def main() -> int:
    args = _parse_args()
    results: list[dict[str, object]] = []

    with HexMazeInterface(debug=args.debug) as hmi:
        for trial_index in range(args.trial_count):
            trial_result: dict[str, object] = {"trial": trial_index}
            try:
                trial_result["result"] = _run_trial(hmi, args.cluster, args)
                trial_result["ok"] = True
            except MazeException as exc:
                trial_result["ok"] = False
                trial_result["error"] = str(exc)
                try:
                    trial_result["positions_mm"] = list(hmi.read_positions_cluster(args.cluster))
                except MazeException:
                    pass
                results.append(trial_result)
                print(
                    json.dumps(
                        {
                            "cluster": args.cluster,
                            "controller_parameters": list(_controller_parameters(args).to_tuple()),
                            "home_parameters": list(_home_parameters(args).to_tuple()),
                            "trials": results,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                raise SystemExit(1) from exc
            results.append(trial_result)

    print(
        json.dumps(
            {
                "cluster": args.cluster,
                "controller_parameters": list(_controller_parameters(args).to_tuple()),
                "home_parameters": list(_home_parameters(args).to_tuple()),
                "trials": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
