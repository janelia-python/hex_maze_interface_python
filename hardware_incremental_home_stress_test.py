#!/usr/bin/env python3
"""Stress test random moves followed by incremental homing on a live cluster."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TextIO

from hex_maze_interface import (
    ControllerParameters,
    HexMazeInterface,
    HomeOutcome,
    HomeParameters,
    MazeException,
)


def _default_log_file() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "logs" / f"incremental_home_stress_{timestamp}.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--trial-count", type=int, default=10)
    parser.add_argument("--random-move-count", type=int, default=3)
    parser.add_argument("--random-low", type=int, default=0)
    parser.add_argument("--random-high", type=int, default=400)
    parser.add_argument("--incremental-home-travel-limit", type=int, default=100)
    parser.add_argument("--max-home-passes", type=int, default=6)
    parser.add_argument("--initial-home-travel-limit", type=int, default=500)
    parser.add_argument("--initial-home-attempts", type=int, default=3)
    parser.add_argument("--home-max-velocity", type=int, default=20)
    parser.add_argument("--home-run-current", type=int, default=50)
    parser.add_argument("--home-stall-threshold", type=int, default=10)
    parser.add_argument("--post-home-target", type=int, default=40)
    parser.add_argument("--post-home-step", type=int, default=0)
    parser.add_argument("--start-velocity", type=int, default=10)
    parser.add_argument("--stop-velocity", type=int, default=10)
    parser.add_argument("--first-velocity", type=int, default=40)
    parser.add_argument("--max-velocity", type=int, default=40)
    parser.add_argument("--first-acceleration", type=int, default=120)
    parser.add_argument("--max-acceleration", type=int, default=80)
    parser.add_argument("--max-deceleration", type=int, default=80)
    parser.add_argument("--first-deceleration", type=int, default=120)
    parser.add_argument("--position-timeout", type=float, default=35.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--power-cycle-before-start", action="store_true")
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="JSONL log path. Defaults to logs/incremental_home_stress_<timestamp>.jsonl.",
    )
    parser.add_argument("--no-log-file", action="store_true")
    parser.add_argument(
        "--success-trace",
        action="store_true",
        help="Include full position polling traces for successful moves.",
    )
    parser.add_argument(
        "--compact-output",
        action="store_true",
        help="Print a compact final summary while keeping full details in the JSONL log.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _json_default(value: object) -> object:
    if isinstance(value, HomeOutcome):
        return value.name
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def _write_event(log: TextIO | None, event: dict[str, object]) -> None:
    if log is None:
        return
    log.write(json.dumps(event, default=_json_default, sort_keys=True) + "\n")
    log.flush()


def _print_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


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


def _home_parameters(args: argparse.Namespace, travel_limit: int) -> HomeParameters:
    return HomeParameters(
        travel_limit=travel_limit,
        max_velocity=args.home_max_velocity,
        run_current=args.home_run_current,
        stall_threshold=args.home_stall_threshold,
    )


def _state_snapshot(hmi: HexMazeInterface, cluster_address: int) -> dict[str, object]:
    snapshot: dict[str, object] = {"cluster_address": cluster_address}
    try:
        snapshot["communicating"] = hmi.communicating_cluster(cluster_address)
    except MazeException as exc:
        snapshot["communicating_error"] = str(exc)
    try:
        snapshot["homed"] = list(hmi.homed_cluster(cluster_address))
    except MazeException as exc:
        snapshot["homed_error"] = str(exc)
    try:
        snapshot["home_outcomes"] = [
            outcome.name for outcome in hmi.read_home_outcomes_cluster(cluster_address)
        ]
    except MazeException as exc:
        snapshot["home_outcomes_error"] = str(exc)
    try:
        snapshot["positions_mm"] = list(hmi.read_positions_cluster(cluster_address))
    except MazeException as exc:
        snapshot["positions_error"] = str(exc)
    try:
        snapshot["run_current_percent"] = hmi.read_run_current_cluster(cluster_address)
    except MazeException as exc:
        snapshot["run_current_error"] = str(exc)
    try:
        snapshot["controller_parameters"] = asdict(
            hmi.read_controller_parameters_cluster(cluster_address)
        )
    except MazeException as exc:
        snapshot["controller_parameters_error"] = str(exc)
    return snapshot


def _wait_for_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    start = time.monotonic()
    deadline = start + timeout_s
    last: dict[str, object] = {}
    samples: list[dict[str, object]] = []

    while time.monotonic() < deadline:
        elapsed_s = time.monotonic() - start
        homed = tuple(bool(value) for value in hmi.homed_cluster(cluster_address))
        outcomes = tuple(hmi.read_home_outcomes_cluster(cluster_address))
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        sample = {
            "elapsed_s": round(elapsed_s, 3),
            "homed": list(homed),
            "outcomes": [outcome.name for outcome in outcomes],
            "positions_mm": list(positions),
        }
        samples.append(sample)
        last = sample

        if any(outcome == HomeOutcome.FAILED for outcome in outcomes):
            raise MazeException(
                f"cluster {cluster_address} reported failed home outcome: "
                f"{[outcome.name for outcome in outcomes]}"
            )
        if all(outcome != HomeOutcome.IN_PROGRESS for outcome in outcomes):
            return {
                "elapsed_s": round(elapsed_s, 3),
                "homed": list(homed),
                "outcomes": [outcome.name for outcome in outcomes],
                "positions_mm": list(positions),
                "sample_count": len(samples),
                "first_sample": samples[0],
                "last_sample": samples[-1],
            }
        time.sleep(poll_interval_s)

    raise MazeException(
        f"cluster {cluster_address} did not finish homing within {timeout_s:.1f}s; "
        f"last state was {last}"
    )


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
        report["attempt"] = attempt_index
        reports.append(report)
        if all(report["homed"]):
            return reports
    raise MazeException(
        f"cluster {cluster_address} did not fully home after {max_attempts} attempts: "
        f"{reports[-1]}"
    )


def _wait_for_positions(
    hmi: HexMazeInterface,
    cluster_address: int,
    targets_mm: tuple[int, ...],
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
    *,
    collect_trace: bool,
) -> tuple[tuple[int, ...], list[dict[str, object]]]:
    start = time.monotonic()
    deadline = start + timeout_s
    trace: list[dict[str, object]] = []
    first_sample: dict[str, object] | None = None
    last_sample: dict[str, object] | None = None

    while time.monotonic() < deadline:
        elapsed_s = time.monotonic() - start
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        sample = {
            "elapsed_s": round(elapsed_s, 3),
            "positions_mm": list(positions),
        }
        if first_sample is None:
            first_sample = sample
        last_sample = sample
        if collect_trace:
            trace.append(sample)

        if all(
            abs(position - target) <= tolerance_mm
            for position, target in zip(positions, targets_mm, strict=True)
        ):
            if not collect_trace:
                trace = [first_sample, last_sample] if first_sample != last_sample else [sample]
            return positions, trace
        time.sleep(poll_interval_s)

    if not collect_trace and first_sample is not None and last_sample is not None:
        trace = [first_sample, last_sample] if first_sample != last_sample else [last_sample]
    raise MazeException(
        f"cluster {cluster_address} did not reach targets {list(targets_mm)} "
        f"within {timeout_s:.1f}s; last sample was {last_sample}"
    )


def _stationary_prisms(
    before_mm: tuple[int, ...],
    after_mm: tuple[int, ...],
    tolerance_mm: int,
) -> list[int]:
    return [
        prism_index
        for prism_index, (before, after) in enumerate(zip(before_mm, after_mm, strict=True))
        if abs(after - before) <= tolerance_mm
    ]


def _post_home_targets(args: argparse.Namespace) -> tuple[int, ...]:
    return tuple(
        args.post_home_target + args.post_home_step * prism_index
        for prism_index in range(HexMazeInterface.PRISM_COUNT)
    )


def _random_targets(args: argparse.Namespace, rng: random.Random) -> tuple[int, ...]:
    return tuple(
        rng.randint(args.random_low, args.random_high)
        for _ in range(HexMazeInterface.PRISM_COUNT)
    )


def _run_random_move(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
    targets_mm: tuple[int, ...],
    move_index: int,
) -> dict[str, object]:
    before_positions = tuple(hmi.read_positions_cluster(cluster_address))
    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        raise MazeException(f"random move {move_index}: write_targets_cluster failed")
    final_positions, trace = _wait_for_positions(
        hmi,
        cluster_address,
        targets_mm,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
        collect_trace=args.success_trace,
    )
    return {
        "move": move_index,
        "before_positions_mm": list(before_positions),
        "targets_mm": list(targets_mm),
        "final_positions_mm": list(final_positions),
        "trace": trace,
    }


def _run_incremental_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    home_parameters = _home_parameters(args, args.incremental_home_travel_limit)
    home_passes: list[dict[str, object]] = []

    for pass_index in range(args.max_home_passes):
        before = _state_snapshot(hmi, cluster_address)
        if not hmi.home_cluster(cluster_address, home_parameters):
            raise MazeException(f"incremental home pass {pass_index}: home_cluster failed")
        report = _wait_for_home(
            hmi,
            cluster_address,
            args.home_timeout,
            args.poll_interval,
        )
        home_pass = {
            "pass": pass_index,
            "home_parameters": asdict(home_parameters),
            "before": before,
            "after": report,
        }
        home_passes.append(home_pass)
        if all(report["homed"]):
            return home_passes

    raise MazeException(
        "incremental homing did not home all prisms after "
        f"{args.max_home_passes} passes; last pass was {home_passes[-1]}"
    )


def _run_post_home_move(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    targets_mm = _post_home_targets(args)
    before_positions = tuple(hmi.read_positions_cluster(cluster_address))
    before_snapshot = _state_snapshot(hmi, cluster_address)
    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        after_snapshot = _state_snapshot(hmi, cluster_address)
        raise MazeException(
            "post-home move: write_targets_cluster failed; "
            f"before={before_snapshot}; after={after_snapshot}"
        )

    try:
        final_positions, trace = _wait_for_positions(
            hmi,
            cluster_address,
            targets_mm,
            args.position_timeout,
            args.poll_interval,
            args.position_tolerance,
            collect_trace=True,
        )
    except MazeException as exc:
        after_positions = tuple(hmi.read_positions_cluster(cluster_address))
        stationary = _stationary_prisms(
            before_positions,
            after_positions,
            args.position_tolerance,
        )
        after_snapshot = _state_snapshot(hmi, cluster_address)
        raise MazeException(
            "post-home move failed; "
            f"stationary_prisms={stationary}; "
            f"before_positions_mm={list(before_positions)}; "
            f"after_positions_mm={list(after_positions)}; "
            f"targets_mm={list(targets_mm)}; "
            f"after_snapshot={after_snapshot}"
        ) from exc

    stationary = _stationary_prisms(before_positions, final_positions, args.position_tolerance)
    if stationary:
        after_snapshot = _state_snapshot(hmi, cluster_address)
        raise MazeException(
            "post-home move reached target but one or more prisms did not launch; "
            f"stationary_prisms={stationary}; "
            f"before_positions_mm={list(before_positions)}; "
            f"final_positions_mm={list(final_positions)}; "
            f"targets_mm={list(targets_mm)}; "
            f"after_snapshot={after_snapshot}"
        )

    return {
        "before_snapshot": before_snapshot,
        "targets_mm": list(targets_mm),
        "final_positions_mm": list(final_positions),
        "stationary_prisms": stationary,
        "trace": trace,
    }


def _run_trial(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
    trial_index: int,
    log: TextIO | None,
) -> dict[str, object]:
    trial_seed = args.seed + cluster_address * 100000 + trial_index
    rng = random.Random(trial_seed)
    result: dict[str, object] = {
        "trial": trial_index,
        "seed": trial_seed,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "ok": False,
    }
    _write_event(log, {"event": "trial_start", **result})

    try:
        random_moves: list[dict[str, object]] = []
        for move_index in range(args.random_move_count):
            targets_mm = _random_targets(args, rng)
            move_result = _run_random_move(
                hmi,
                cluster_address,
                args,
                targets_mm,
                move_index,
            )
            random_moves.append(move_result)
            _write_event(
                log,
                {
                    "event": "random_move",
                    "trial": trial_index,
                    "seed": trial_seed,
                    "cluster": cluster_address,
                    "result": move_result,
                },
            )

        home_passes = _run_incremental_home(hmi, cluster_address, args)
        _write_event(
            log,
            {
                "event": "incremental_home",
                "trial": trial_index,
                "seed": trial_seed,
                "cluster": cluster_address,
                "home_passes": home_passes,
            },
        )

        post_home_move = _run_post_home_move(hmi, cluster_address, args)
        _write_event(
            log,
            {
                "event": "post_home_move",
                "trial": trial_index,
                "seed": trial_seed,
                "cluster": cluster_address,
                "result": post_home_move,
            },
        )

        result.update(
            {
                "ok": True,
                "random_moves": random_moves,
                "home_passes": home_passes,
                "post_home_move": post_home_move,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        _write_event(log, {"event": "trial_success", **result})
        return result
    except MazeException as exc:
        failure_snapshot = _state_snapshot(hmi, cluster_address)
        result.update(
            {
                "ok": False,
                "error": str(exc),
                "failure_snapshot": failure_snapshot,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        _write_event(log, {"event": "trial_failure", **result})
        return result


def _prepare_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    if not hmi.verify_cluster(cluster_address)["checks"].get("communicating", False):
        raise MazeException(f"cluster {cluster_address} failed communication check")
    if args.power_cycle_before_start:
        if not hmi.power_off_cluster(cluster_address):
            raise MazeException(f"cluster {cluster_address} failed power_off_cluster")
        if not hmi.power_on_cluster(cluster_address):
            raise MazeException(f"cluster {cluster_address} failed power_on_cluster")

    controller_parameters = _controller_parameters(args)
    if not hmi.write_controller_parameters_cluster(cluster_address, controller_parameters):
        raise MazeException("write_controller_parameters_cluster failed")

    initial_home_parameters = _home_parameters(args, args.initial_home_travel_limit)
    initial_home = _home_until_all_homed(
        hmi,
        cluster_address,
        initial_home_parameters,
        args.home_timeout,
        args.poll_interval,
        args.initial_home_attempts,
    )
    return {
        "initial_snapshot": _state_snapshot(hmi, cluster_address),
        "controller_parameters": asdict(controller_parameters),
        "initial_home_parameters": asdict(initial_home_parameters),
        "initial_home": initial_home,
    }


def _validate_args(args: argparse.Namespace) -> None:
    if args.random_low < 0:
        raise MazeException("--random-low must be non-negative")
    if args.random_low >= args.random_high:
        raise MazeException("--random-low must be less than --random-high")
    if args.random_high > 550:
        raise MazeException("--random-high must stay within the 0..550 mm firmware-safe range")
    if args.post_home_target < 0:
        raise MazeException("--post-home-target must be non-negative")
    max_post_home_target = args.post_home_target + args.post_home_step * (
        HexMazeInterface.PRISM_COUNT - 1
    )
    if max_post_home_target > 550:
        raise MazeException("post-home targets must stay within the 0..550 mm range")
    if args.incremental_home_travel_limit <= 0:
        raise MazeException("--incremental-home-travel-limit must be positive")
    if args.max_home_passes <= 0:
        raise MazeException("--max-home-passes must be positive")


def _trial_compact_summary(trial: dict[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {
        "trial": trial.get("trial"),
        "seed": trial.get("seed"),
        "ok": trial.get("ok"),
        "started_at": trial.get("started_at"),
        "finished_at": trial.get("finished_at"),
    }
    if not trial.get("ok"):
        compact["error"] = trial.get("error")
        compact["failure_snapshot"] = trial.get("failure_snapshot")
        return compact

    random_moves = list(trial.get("random_moves", []))
    home_passes = list(trial.get("home_passes", []))
    post_home_move = dict(trial.get("post_home_move", {}))
    targets = [
        target
        for move in random_moves
        for target in dict(move).get("targets_mm", [])
    ]
    observed_positions = [
        position
        for move in random_moves
        for position in dict(move).get("final_positions_mm", [])
    ]
    compact.update(
        {
            "random_move_count": len(random_moves),
            "home_pass_count": len(home_passes),
            "max_random_target_mm": max(targets) if targets else None,
            "max_observed_random_position_mm": (
                max(observed_positions) if observed_positions else None
            ),
            "post_home_targets_mm": post_home_move.get("targets_mm"),
            "post_home_final_positions_mm": post_home_move.get("final_positions_mm"),
            "post_home_stationary_prisms": post_home_move.get("stationary_prisms"),
        }
    )
    return compact


def _compact_summary(summary: dict[str, object]) -> dict[str, object]:
    trials = list(summary.get("trials", []))
    compact: dict[str, object] = {
        "cluster": summary.get("cluster"),
        "ok": summary.get("ok"),
        "started_at": summary.get("started_at"),
        "finished_at": summary.get("finished_at"),
        "log_file": summary.get("log_file"),
        "trial_count": len(trials),
        "failure_trial": summary.get("failure_trial"),
        "trials": [_trial_compact_summary(dict(trial)) for trial in trials],
    }
    if "preparation_error" in summary:
        compact["preparation_error"] = summary["preparation_error"]
        compact["preparation_snapshot"] = summary.get("preparation_snapshot")
    return compact


def _print_summary(summary: dict[str, object], args: argparse.Namespace) -> None:
    printable_summary = _compact_summary(summary) if args.compact_output else summary
    print(json.dumps(printable_summary, default=_json_default, indent=2, sort_keys=True))


def main() -> int:
    args = _parse_args()
    _validate_args(args)

    log_file = None if args.no_log_file else args.log_file or _default_log_file()
    log: TextIO | None = None
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log = log_file.open("w", encoding="utf-8")

    results: list[dict[str, object]] = []
    arguments = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }
    summary: dict[str, object] = {
        "cluster": args.cluster,
        "arguments": arguments,
        "log_file": str(log_file) if log_file is not None else None,
        "ok": False,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "trials": results,
    }

    try:
        _write_event(log, {"event": "run_start", **summary})
        with HexMazeInterface(debug=args.debug) as hmi:
            try:
                preparation = _prepare_cluster(hmi, args.cluster, args)
            except MazeException as exc:
                summary["preparation_error"] = str(exc)
                summary["preparation_snapshot"] = _state_snapshot(hmi, args.cluster)
                summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
                _write_event(log, {"event": "preparation_failure", **summary})
                _print_summary(summary, args)
                return 1

            summary["preparation"] = preparation
            _write_event(log, {"event": "prepared", "cluster": args.cluster, **preparation})

            for trial_index in range(args.trial_count):
                _print_progress(
                    f"trial {trial_index + 1}/{args.trial_count}: "
                    f"{args.random_move_count} random moves, incremental home, post-home move"
                )
                trial_result = _run_trial(hmi, args.cluster, args, trial_index, log)
                results.append(trial_result)
                if not trial_result["ok"]:
                    summary["failure_trial"] = trial_index
                    summary["ok"] = False
                    break
            else:
                summary["ok"] = True

        summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_event(log, {"event": "run_finish", **summary})
        _print_summary(summary, args)
        return 0 if summary["ok"] else 1
    finally:
        if log is not None:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
