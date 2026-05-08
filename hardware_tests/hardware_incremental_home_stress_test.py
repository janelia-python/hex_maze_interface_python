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

DEFAULT_RANDOM_HIGH_MM = 120
DEFAULT_INITIAL_HOME_TRAVEL_LIMIT_MM = 100
DEFAULT_INITIAL_HOME_ATTEMPTS = 7
DEFAULT_INITIAL_HOME_MAX_VELOCITY = 10
DEFAULT_INITIAL_HOME_RUN_CURRENT = 43
DEFAULT_INITIAL_HOME_STALL_THRESHOLD = 0
DEFAULT_INITIAL_HOME_TIMEOUT_S = 25.0
DEFAULT_STALL_PLAUSIBILITY_TOLERANCE_MM = 2
EXTENDED_RANDOM_RANGE_THRESHOLD_MM = 150
SAFE_START_VELOCITY = 10
SAFE_STOP_VELOCITY = 10
SAFE_FIRST_VELOCITY = 40
SAFE_MAX_VELOCITY = 40
SAFE_FIRST_ACCELERATION = 120
SAFE_MAX_ACCELERATION = 80
SAFE_MAX_DECELERATION = 80
SAFE_FIRST_DECELERATION = 120
SAFE_HOME_MAX_VELOCITY = 10
SAFE_HOME_RUN_CURRENT = 43
SAFE_HOME_STALL_THRESHOLD = 0
UINT8_MIN = 0
UINT8_MAX = 255
INT8_MIN = -128
INT8_MAX = 127


def _default_log_file() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "logs" / f"incremental_home_stress_{timestamp}.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--trial-count", type=int, default=10)
    parser.add_argument("--random-move-count", type=int, default=3)
    parser.add_argument(
        "--random-move-mode",
        choices=("single", "double", "mixed"),
        default="single",
        help=(
            "Use normal cluster targets, queued double-target moves, or a deterministic "
            "mix during the pre-home random movement phase."
        ),
    )
    parser.add_argument("--random-low", type=int, default=0)
    parser.add_argument("--random-high", type=int, default=DEFAULT_RANDOM_HIGH_MM)
    parser.add_argument(
        "--allow-extended-random-range",
        action="store_true",
        help=(
            "Allow random pre-home targets above "
            f"{EXTENDED_RANDOM_RANGE_THRESHOLD_MM} mm. Use only after confirming rig clearance."
        ),
    )
    parser.add_argument("--incremental-home-travel-limit", type=int, default=100)
    parser.add_argument("--max-home-passes", type=int, default=6)
    parser.add_argument(
        "--initial-home-travel-limit",
        type=int,
        default=DEFAULT_INITIAL_HOME_TRAVEL_LIMIT_MM,
    )
    parser.add_argument("--initial-home-attempts", type=int, default=DEFAULT_INITIAL_HOME_ATTEMPTS)
    parser.add_argument(
        "--initial-home-mode",
        choices=("ordinary", "recovery"),
        default="ordinary",
        help=(
            "Use ordinary repeated 100 mm homing for researcher-shaped runs, or "
            "explicit recovery homing for rare fully automated preparation. "
            "Recovery mode should normally use --initial-home-travel-limit 550."
        ),
    )
    parser.add_argument(
        "--initial-home-max-velocity",
        type=int,
        default=DEFAULT_INITIAL_HOME_MAX_VELOCITY,
    )
    parser.add_argument(
        "--initial-home-run-current",
        type=int,
        default=DEFAULT_INITIAL_HOME_RUN_CURRENT,
    )
    parser.add_argument(
        "--initial-home-stall-threshold",
        type=int,
        default=DEFAULT_INITIAL_HOME_STALL_THRESHOLD,
    )
    parser.add_argument(
        "--initial-home-timeout",
        type=float,
        default=DEFAULT_INITIAL_HOME_TIMEOUT_S,
    )
    parser.add_argument("--home-max-velocity", type=int, default=SAFE_HOME_MAX_VELOCITY)
    parser.add_argument("--home-run-current", type=int, default=SAFE_HOME_RUN_CURRENT)
    parser.add_argument("--home-stall-threshold", type=int, default=SAFE_HOME_STALL_THRESHOLD)
    parser.add_argument("--post-home-target", type=int, default=40)
    parser.add_argument("--post-home-step", type=int, default=0)
    parser.add_argument(
        "--post-home-move-mode",
        choices=("single", "double"),
        default="single",
        help="Use normal cluster targets or queued double-targets for the first post-home move.",
    )
    parser.add_argument("--start-velocity", type=int, default=SAFE_START_VELOCITY)
    parser.add_argument("--stop-velocity", type=int, default=SAFE_STOP_VELOCITY)
    parser.add_argument("--first-velocity", type=int, default=SAFE_FIRST_VELOCITY)
    parser.add_argument("--max-velocity", type=int, default=SAFE_MAX_VELOCITY)
    parser.add_argument("--first-acceleration", type=int, default=SAFE_FIRST_ACCELERATION)
    parser.add_argument("--max-acceleration", type=int, default=SAFE_MAX_ACCELERATION)
    parser.add_argument("--max-deceleration", type=int, default=SAFE_MAX_DECELERATION)
    parser.add_argument("--first-deceleration", type=int, default=SAFE_FIRST_DECELERATION)
    parser.add_argument(
        "--allow-aggressive-motion-settings",
        action="store_true",
        help=(
            "Allow velocity or acceleration values above the current desk-rig safe profile. "
            "Use only for supervised tuning; audible slipping invalidates a passing run."
        ),
    )
    parser.add_argument(
        "--allow-clamped-controller-readback",
        action="store_true",
        help=(
            "Allow controller parameter readback to differ from the requested values. "
            "Use this only when testing firmware-side clamps for unsafe requested values."
        ),
    )
    parser.add_argument(
        "--recover-on-move-timeout",
        action="store_true",
        help=(
            "On a movement timeout, lower start/stop velocity, reissue the final target, "
            "and log whether recovery succeeds without reset or re-home."
        ),
    )
    parser.add_argument("--recovery-start-velocity", type=int, default=SAFE_START_VELOCITY)
    parser.add_argument("--recovery-stop-velocity", type=int, default=SAFE_STOP_VELOCITY)
    parser.add_argument("--recovery-first-velocity", type=int, default=SAFE_FIRST_VELOCITY)
    parser.add_argument("--recovery-max-velocity", type=int, default=SAFE_MAX_VELOCITY)
    parser.add_argument(
        "--recovery-first-acceleration",
        type=int,
        default=SAFE_FIRST_ACCELERATION,
    )
    parser.add_argument(
        "--recovery-max-acceleration",
        type=int,
        default=SAFE_MAX_ACCELERATION,
    )
    parser.add_argument("--recovery-max-deceleration", type=int, default=SAFE_MAX_DECELERATION)
    parser.add_argument(
        "--recovery-first-deceleration",
        type=int,
        default=SAFE_FIRST_DECELERATION,
    )
    parser.add_argument("--position-timeout", type=float, default=35.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=1)
    parser.add_argument(
        "--stall-plausibility-tolerance",
        type=int,
        default=DEFAULT_STALL_PLAUSIBILITY_TOLERANCE_MM,
        help=(
            "Fail if a STALL home outcome reports last_home_travel_mm more than this "
            "many millimeters short of the prism's pre-home position."
        ),
    )
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


def _recovery_controller_parameters(args: argparse.Namespace) -> ControllerParameters:
    return ControllerParameters(
        start_velocity=args.recovery_start_velocity,
        stop_velocity=args.recovery_stop_velocity,
        first_velocity=args.recovery_first_velocity,
        max_velocity=args.recovery_max_velocity,
        first_acceleration=args.recovery_first_acceleration,
        max_acceleration=args.recovery_max_acceleration,
        max_deceleration=args.recovery_max_deceleration,
        first_deceleration=args.recovery_first_deceleration,
    )


def _verify_controller_parameters(
    hmi: HexMazeInterface,
    cluster_address: int,
    expected: ControllerParameters,
    allow_clamped_readback: bool = False,
) -> ControllerParameters:
    actual = hmi.read_controller_parameters_cluster(cluster_address)
    if actual.to_tuple() != expected.to_tuple():
        if allow_clamped_readback:
            return actual
        raise MazeException(
            "controller parameter readback mismatch: "
            f"expected={asdict(expected)}, actual={asdict(actual)}"
        )
    return actual


def _home_parameters(args: argparse.Namespace, travel_limit: int) -> HomeParameters:
    return HomeParameters(
        travel_limit=travel_limit,
        max_velocity=args.home_max_velocity,
        run_current=args.home_run_current,
        stall_threshold=args.home_stall_threshold,
    )


def _initial_home_parameters(args: argparse.Namespace) -> HomeParameters:
    return HomeParameters(
        travel_limit=args.initial_home_travel_limit,
        max_velocity=args.initial_home_max_velocity,
        run_current=args.initial_home_run_current,
        stall_threshold=args.initial_home_stall_threshold,
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
    diagnostics = _diagnostics_snapshot(hmi, cluster_address)
    if isinstance(diagnostics, dict):
        snapshot["prism_diagnostics_error"] = diagnostics["error"]
    else:
        snapshot["prism_diagnostics"] = diagnostics
    return snapshot


def _diagnostics_snapshot(
    hmi: HexMazeInterface,
    cluster_address: int,
) -> list[dict[str, object]] | dict[str, str]:
    try:
        return [
            asdict(diagnostics)
            for diagnostics in hmi.read_prism_diagnostics_cluster(cluster_address)
        ]
    except MazeException as exc:
        return {"error": str(exc)}


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
            time.sleep(poll_interval_s)
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
            if any(outcome == HomeOutcome.FAILED for outcome in outcomes):
                raise MazeException(
                    f"cluster {cluster_address} reported failed home outcome: "
                    f"{[outcome.name for outcome in outcomes]}"
                )
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

    try:
        hmi.pause_cluster(cluster_address)
    except MazeException as exc:
        pause_status = f"; pause_cluster also failed: {exc}"
    else:
        pause_status = "; pause_cluster was sent"
    raise MazeException(
        f"cluster {cluster_address} did not finish homing within {timeout_s:.1f}s; "
        f"last state was {last}{pause_status}"
    )


def _home_until_all_homed(
    hmi: HexMazeInterface,
    cluster_address: int,
    home_parameters: HomeParameters,
    timeout_s: float,
    poll_interval_s: float,
    position_tolerance_mm: int,
    stall_plausibility_tolerance_mm: int,
    max_attempts: int,
    *,
    retry_unhomed_only: bool,
    recovery_home: bool,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    unhomed_prisms = tuple(range(HexMazeInterface.PRISM_COUNT))
    for attempt_index in range(max_attempts):
        if attempt_index == 0 or not retry_unhomed_only:
            home_scope = "cluster"
            homed_prisms: tuple[int, ...] = tuple(range(HexMazeInterface.PRISM_COUNT))
            home_started = (
                hmi.recovery_home_cluster(cluster_address, home_parameters)
                if recovery_home
                else hmi.home_cluster(cluster_address, home_parameters)
            )
            if not home_started:
                raise MazeException(
                    f"cluster {cluster_address} failed to start homing on attempt {attempt_index}"
                )
        else:
            home_scope = "prisms"
            homed_prisms = unhomed_prisms
            for prism_address in unhomed_prisms:
                home_started = (
                    hmi.recovery_home_prism(cluster_address, prism_address, home_parameters)
                    if recovery_home
                    else hmi.home_prism(cluster_address, prism_address, home_parameters)
                )
                if not home_started:
                    raise MazeException(
                        "cluster "
                        f"{cluster_address} failed to start homing prism {prism_address} "
                        f"on attempt {attempt_index}"
                    )
        before_positions = tuple(hmi.read_positions_cluster(cluster_address))
        report = _wait_for_home(hmi, cluster_address, timeout_s, poll_interval_s)
        report["attempt"] = attempt_index
        report["home_scope"] = home_scope
        report["home_mode"] = "recovery" if recovery_home else "ordinary"
        report["homed_prisms"] = list(homed_prisms)
        report["before_positions_mm"] = list(before_positions)
        report["prism_diagnostics"] = _diagnostics_snapshot(hmi, cluster_address)
        _raise_on_implausible_stall(
            report,
            before_positions,
            report["prism_diagnostics"],
            homed_prisms,
            stall_plausibility_tolerance_mm,
            "initial home",
        )
        reports.append(report)
        if all(report["homed"]):
            return reports
        _raise_on_target_reached_within_home_range(
            report,
            before_positions,
            home_parameters.travel_limit,
            position_tolerance_mm,
            "initial home",
        )
        unhomed_prisms = tuple(
            prism_index for prism_index, homed in enumerate(report["homed"]) if not homed
        )
        if not unhomed_prisms:
            return reports
    raise MazeException(
        f"cluster {cluster_address} did not fully home after {max_attempts} attempts: {reports[-1]}"
    )


def _home_start(
    hmi: HexMazeInterface,
    cluster_address: int,
    home_parameters: HomeParameters,
    home_prisms: tuple[int, ...],
) -> None:
    if len(home_prisms) == HexMazeInterface.PRISM_COUNT:
        if not hmi.home_cluster(cluster_address, home_parameters):
            raise MazeException(f"cluster {cluster_address}: home_cluster failed")
        return

    for prism_address in home_prisms:
        if not hmi.home_prism(cluster_address, prism_address, home_parameters):
            raise MazeException(f"cluster {cluster_address}: home_prism {prism_address} failed")


def _unhomed_prisms(report: dict[str, object]) -> tuple[int, ...]:
    homed_values = tuple(bool(value) for value in report["homed"])
    return tuple(prism_index for prism_index, homed in enumerate(homed_values) if not homed)


def _target_reached_within_home_range_prisms(
    report: dict[str, object],
    before_positions_mm: tuple[int, ...],
    travel_limit_mm: int,
    position_tolerance_mm: int,
) -> tuple[int, ...]:
    homed_values = tuple(bool(value) for value in report["homed"])
    outcomes = tuple(str(value).upper() for value in report["outcomes"])
    return tuple(
        prism_index
        for prism_index, (homed, outcome) in enumerate(zip(homed_values, outcomes, strict=True))
        if not homed
        and outcome == HomeOutcome.TARGET_REACHED.name
        and before_positions_mm[prism_index] <= travel_limit_mm + position_tolerance_mm
    )


def _raise_on_target_reached_within_home_range(
    report: dict[str, object],
    before_positions_mm: tuple[int, ...],
    travel_limit_mm: int,
    position_tolerance_mm: int,
    context: str,
) -> None:
    affected_prisms = _target_reached_within_home_range_prisms(
        report,
        before_positions_mm,
        travel_limit_mm,
        position_tolerance_mm,
    )
    if not affected_prisms:
        return
    raise MazeException(
        f"{context}: prisms {list(affected_prisms)} started within the "
        f"{travel_limit_mm} mm home travel range but reached the travel limit "
        "without StallGuard homing; aborting instead of retrying the same "
        f"grinding home pass; before_positions_mm={list(before_positions_mm)}; "
        f"report={report}"
    )


def _raise_on_implausible_stall(
    report: dict[str, object],
    before_positions_mm: tuple[int, ...],
    diagnostics: object,
    homed_prisms: tuple[int, ...],
    tolerance_mm: int,
    context: str,
) -> None:
    outcomes = tuple(str(value).upper() for value in report["outcomes"])
    stall_prisms = tuple(
        prism_index
        for prism_index in homed_prisms
        if outcomes[prism_index] == HomeOutcome.STALL.name
    )
    if not stall_prisms:
        return
    if isinstance(diagnostics, dict):
        raise MazeException(
            f"{context}: cannot validate STALL plausibility because diagnostics "
            f"read failed: {diagnostics}"
        )

    diagnostic_rows = list(diagnostics)
    affected: list[dict[str, int]] = []
    for prism_index in stall_prisms:
        expected_start_mm = max(0, int(before_positions_mm[prism_index]))
        if expected_start_mm <= tolerance_mm:
            continue
        try:
            last_home_travel_mm = int(
                dict(diagnostic_rows[prism_index])["last_home_travel_mm"]
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise MazeException(
                f"{context}: diagnostics did not include last_home_travel_mm "
                f"for prism {prism_index}: {diagnostics}"
            ) from exc
        if last_home_travel_mm + tolerance_mm < expected_start_mm:
            affected.append(
                {
                    "prism": prism_index,
                    "before_position_mm": expected_start_mm,
                    "last_home_travel_mm": last_home_travel_mm,
                    "tolerance_mm": tolerance_mm,
                }
            )
    if not affected:
        return
    raise MazeException(
        f"{context}: implausible STALL home outcome(s) detected; aborting "
        f"instead of trusting a possible false zero: {affected}; report={report}"
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
            time.sleep(poll_interval_s)
            settled_positions = tuple(hmi.read_positions_cluster(cluster_address))
            settled_sample = {
                "elapsed_s": round(time.monotonic() - start, 3),
                "positions_mm": list(settled_positions),
            }
            last_sample = settled_sample
            if collect_trace:
                trace.append(settled_sample)
            if all(
                abs(position - target) <= tolerance_mm
                for position, target in zip(settled_positions, targets_mm, strict=True)
            ):
                if not collect_trace:
                    trace = (
                        [first_sample, last_sample]
                        if first_sample != last_sample
                        else [settled_sample]
                    )
                return settled_positions, trace
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
        rng.randint(args.random_low, args.random_high) for _ in range(HexMazeInterface.PRISM_COUNT)
    )


def _double_target_pairs(
    before_mm: tuple[int, ...],
    targets_mm: tuple[int, ...],
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (before + ((target - before) // 2), target)
        for before, target in zip(before_mm, targets_mm, strict=True)
    )


def _resolve_random_move_mode(args: argparse.Namespace, rng: random.Random) -> str:
    if args.random_move_mode == "mixed":
        return rng.choice(("single", "double"))
    return args.random_move_mode


def _write_cluster_targets(
    hmi: HexMazeInterface,
    cluster_address: int,
    before_positions: tuple[int, ...],
    targets_mm: tuple[int, ...],
    move_mode: str,
) -> dict[str, object]:
    if move_mode == "single":
        if not hmi.write_targets_cluster(cluster_address, targets_mm):
            raise MazeException("write_targets_cluster failed")
        return {"move_mode": move_mode}

    double_targets_mm = _double_target_pairs(before_positions, targets_mm)
    if not hmi.write_double_targets_cluster(cluster_address, double_targets_mm):
        raise MazeException("write_double_targets_cluster failed")
    return {
        "move_mode": move_mode,
        "double_targets_mm": [list(pair) for pair in double_targets_mm],
    }


def _recover_move_timeout(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
    before_positions: tuple[int, ...],
    targets_mm: tuple[int, ...],
) -> dict[str, object]:
    positions_before_recovery = tuple(hmi.read_positions_cluster(cluster_address))
    diagnostics_before_recovery = _diagnostics_snapshot(hmi, cluster_address)
    recovery_parameters = _recovery_controller_parameters(args)
    if not hmi.write_controller_parameters_cluster(cluster_address, recovery_parameters):
        raise MazeException("recovery write_controller_parameters_cluster failed")
    actual_recovery_parameters = _verify_controller_parameters(
        hmi,
        cluster_address,
        recovery_parameters,
        args.allow_clamped_controller_readback,
    )
    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        raise MazeException("recovery write_targets_cluster failed")
    recovered_positions, recovery_trace = _wait_for_positions(
        hmi,
        cluster_address,
        targets_mm,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
        collect_trace=True,
    )
    return {
        "recovered": True,
        "recovery_controller_parameters": asdict(recovery_parameters),
        "actual_recovery_controller_parameters": asdict(actual_recovery_parameters),
        "positions_before_recovery_mm": list(positions_before_recovery),
        "diagnostics_before_recovery": diagnostics_before_recovery,
        "diagnostics_after_recovery": _diagnostics_snapshot(hmi, cluster_address),
        "stationary_before_recovery": _stationary_prisms(
            before_positions,
            positions_before_recovery,
            args.position_tolerance,
        ),
        "recovered_positions_mm": list(recovered_positions),
        "recovery_trace": recovery_trace,
    }


def _run_random_move(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
    targets_mm: tuple[int, ...],
    rng: random.Random,
    move_index: int,
) -> dict[str, object]:
    before_positions = tuple(hmi.read_positions_cluster(cluster_address))
    move_mode = _resolve_random_move_mode(args, rng)
    try:
        write_report = _write_cluster_targets(
            hmi,
            cluster_address,
            before_positions,
            targets_mm,
            move_mode,
        )
    except MazeException as exc:
        raise MazeException(f"random move {move_index}: {exc}") from exc
    try:
        final_positions, trace = _wait_for_positions(
            hmi,
            cluster_address,
            targets_mm,
            args.position_timeout,
            args.poll_interval,
            args.position_tolerance,
            collect_trace=args.success_trace,
        )
        recovery_report: dict[str, object] = {"recovered": False}
    except MazeException as exc:
        if not args.recover_on_move_timeout:
            raise
        try:
            recovery_report = _recover_move_timeout(
                hmi,
                cluster_address,
                args,
                before_positions,
                targets_mm,
            )
            final_positions = tuple(recovery_report["recovered_positions_mm"])
            trace = []
        except MazeException as recovery_exc:
            raise MazeException(f"{exc}; recovery failed: {recovery_exc}") from recovery_exc

    return {
        "move": move_index,
        **write_report,
        **recovery_report,
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
    home_prisms = tuple(range(HexMazeInterface.PRISM_COUNT))

    for pass_index in range(args.max_home_passes):
        before = _state_snapshot(hmi, cluster_address)
        _home_start(hmi, cluster_address, home_parameters, home_prisms)
        report = _wait_for_home(
            hmi,
            cluster_address,
            args.home_timeout,
            args.poll_interval,
        )
        home_pass = {
            "pass": pass_index,
            "home_scope": (
                "cluster" if len(home_prisms) == HexMazeInterface.PRISM_COUNT else "prisms"
            ),
            "homed_prisms": list(home_prisms),
            "home_parameters": asdict(home_parameters),
            "before": before,
            "after": report,
        }
        after_diagnostics = _diagnostics_snapshot(hmi, cluster_address)
        home_pass["after_prism_diagnostics"] = after_diagnostics
        before_positions = tuple(int(position) for position in before["positions_mm"])
        _raise_on_implausible_stall(
            report,
            before_positions,
            after_diagnostics,
            home_prisms,
            args.stall_plausibility_tolerance,
            "incremental home",
        )
        home_passes.append(home_pass)
        if all(report["homed"]):
            return home_passes
        _raise_on_target_reached_within_home_range(
            report,
            before_positions,
            home_parameters.travel_limit,
            args.position_tolerance,
            "incremental home",
        )
        home_prisms = _unhomed_prisms(report)

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
    try:
        write_report = _write_cluster_targets(
            hmi,
            cluster_address,
            before_positions,
            targets_mm,
            args.post_home_move_mode,
        )
    except MazeException as exc:
        after_snapshot = _state_snapshot(hmi, cluster_address)
        raise MazeException(
            f"post-home move: {exc}; before={before_snapshot}; after={after_snapshot}"
        ) from exc

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
        if not args.recover_on_move_timeout:
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
        try:
            recovery_report = _recover_move_timeout(
                hmi,
                cluster_address,
                args,
                before_positions,
                targets_mm,
            )
            final_positions = tuple(recovery_report["recovered_positions_mm"])
            trace = []
        except MazeException as recovery_exc:
            raise MazeException(f"post-home move failed; recovery failed: {recovery_exc}") from (
                recovery_exc
            )
    else:
        recovery_report = {"recovered": False}

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
        **write_report,
        **recovery_report,
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
                rng,
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
    if not hmi.resume_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} failed resume_cluster")

    controller_parameters = _controller_parameters(args)
    if not hmi.write_controller_parameters_cluster(cluster_address, controller_parameters):
        raise MazeException("write_controller_parameters_cluster failed")
    actual_controller_parameters = _verify_controller_parameters(
        hmi,
        cluster_address,
        controller_parameters,
        args.allow_clamped_controller_readback,
    )

    initial_home_parameters = _initial_home_parameters(args)
    initial_home = _home_until_all_homed(
        hmi,
        cluster_address,
        initial_home_parameters,
        args.initial_home_timeout,
        args.poll_interval,
        args.position_tolerance,
        args.stall_plausibility_tolerance,
        args.initial_home_attempts,
        retry_unhomed_only=True,
        recovery_home=args.initial_home_mode == "recovery",
    )
    return {
        "initial_snapshot": _state_snapshot(hmi, cluster_address),
        "controller_parameters": asdict(controller_parameters),
        "actual_controller_parameters": asdict(actual_controller_parameters),
        "initial_home_mode": args.initial_home_mode,
        "initial_home_parameters": asdict(initial_home_parameters),
        "initial_home": initial_home,
    }


def _validate_args(args: argparse.Namespace) -> None:
    safe_motion_limits = {
        "initial_home_max_velocity": SAFE_HOME_MAX_VELOCITY,
        "home_max_velocity": SAFE_HOME_MAX_VELOCITY,
        "start_velocity": SAFE_START_VELOCITY,
        "stop_velocity": SAFE_STOP_VELOCITY,
        "first_velocity": SAFE_FIRST_VELOCITY,
        "max_velocity": SAFE_MAX_VELOCITY,
        "first_acceleration": SAFE_FIRST_ACCELERATION,
        "max_acceleration": SAFE_MAX_ACCELERATION,
        "max_deceleration": SAFE_MAX_DECELERATION,
        "first_deceleration": SAFE_FIRST_DECELERATION,
    }
    uint8_options = (
        "initial_home_max_velocity",
        "initial_home_run_current",
        "home_max_velocity",
        "home_run_current",
        "start_velocity",
        "stop_velocity",
        "first_velocity",
        "max_velocity",
        "first_acceleration",
        "max_acceleration",
        "max_deceleration",
        "first_deceleration",
        "recovery_start_velocity",
        "recovery_stop_velocity",
        "recovery_first_velocity",
        "recovery_max_velocity",
        "recovery_first_acceleration",
        "recovery_max_acceleration",
        "recovery_max_deceleration",
        "recovery_first_deceleration",
    )
    for option_name in uint8_options:
        option_value = getattr(args, option_name)
        if option_value < UINT8_MIN or option_value > UINT8_MAX:
            raise MazeException(f"--{option_name.replace('_', '-')} must be in 0..255")
    aggressive_options = {
        option_name: getattr(args, option_name)
        for option_name, safe_limit in safe_motion_limits.items()
        if getattr(args, option_name) > safe_limit
    }
    if aggressive_options and not args.allow_aggressive_motion_settings:
        formatted_options = ", ".join(
            f"--{option_name.replace('_', '-')}={option_value}"
            for option_name, option_value in aggressive_options.items()
        )
        raise MazeException(
            "aggressive motion settings require --allow-aggressive-motion-settings: "
            f"{formatted_options}"
        )
    unsafe_ramp_profiles = []
    if args.stop_velocity < SAFE_STOP_VELOCITY:
        unsafe_ramp_profiles.append(f"--stop-velocity={args.stop_velocity}")
    if args.stop_velocity < args.start_velocity:
        unsafe_ramp_profiles.append(
            f"--stop-velocity={args.stop_velocity} < --start-velocity={args.start_velocity}"
        )
    if args.recovery_stop_velocity < SAFE_STOP_VELOCITY:
        unsafe_ramp_profiles.append(
            f"--recovery-stop-velocity={args.recovery_stop_velocity}"
        )
    if args.recovery_stop_velocity < args.recovery_start_velocity:
        unsafe_ramp_profiles.append(
            "--recovery-stop-velocity="
            f"{args.recovery_stop_velocity} < "
            f"--recovery-start-velocity={args.recovery_start_velocity}"
        )
    if unsafe_ramp_profiles and not args.allow_aggressive_motion_settings:
        raise MazeException(
            "unsafe ramp profiles require --allow-aggressive-motion-settings: "
            + ", ".join(unsafe_ramp_profiles)
        )
    int8_options = ("initial_home_stall_threshold", "home_stall_threshold")
    for option_name in int8_options:
        option_value = getattr(args, option_name)
        if option_value < INT8_MIN or option_value > INT8_MAX:
            raise MazeException(f"--{option_name.replace('_', '-')} must be in -128..127")
    if args.random_low < 0:
        raise MazeException("--random-low must be non-negative")
    if args.random_low >= args.random_high:
        raise MazeException("--random-low must be less than --random-high")
    if (
        args.random_high > EXTENDED_RANDOM_RANGE_THRESHOLD_MM
        and not args.allow_extended_random_range
    ):
        raise MazeException(
            f"--random-high above {EXTENDED_RANDOM_RANGE_THRESHOLD_MM} mm requires "
            "--allow-extended-random-range"
        )
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
    if args.initial_home_travel_limit <= 0:
        raise MazeException("--initial-home-travel-limit must be positive")
    if args.initial_home_mode == "recovery" and args.initial_home_travel_limit < 550:
        raise MazeException(
            "--initial-home-mode recovery is for fully automated preparation and "
            "requires --initial-home-travel-limit 550; use ordinary mode for "
            "staged researcher-style 100 mm homes"
        )
    if args.initial_home_attempts <= 0:
        raise MazeException("--initial-home-attempts must be positive")
    if args.initial_home_timeout <= 0:
        raise MazeException("--initial-home-timeout must be positive")
    if args.max_home_passes <= 0:
        raise MazeException("--max-home-passes must be positive")
    if args.stall_plausibility_tolerance < 0:
        raise MazeException("--stall-plausibility-tolerance must be non-negative")


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
    targets = [target for move in random_moves for target in dict(move).get("targets_mm", [])]
    observed_positions = [
        position for move in random_moves for position in dict(move).get("final_positions_mm", [])
    ]
    compact.update(
        {
            "random_move_count": len(random_moves),
            "random_move_modes": [dict(move).get("move_mode") for move in random_moves],
            "recovered_random_move_count": sum(
                1 for move in random_moves if dict(move).get("recovered")
            ),
            "home_pass_count": len(home_passes),
            "max_random_target_mm": max(targets) if targets else None,
            "max_observed_random_position_mm": (
                max(observed_positions) if observed_positions else None
            ),
            "post_home_move_mode": post_home_move.get("move_mode"),
            "post_home_recovered": post_home_move.get("recovered"),
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
        key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
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
