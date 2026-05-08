#!/usr/bin/env python3
"""Exercise a researcher-shaped day on a live cluster."""

from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import nullcontext
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

SAFE_CONTROLLER_PARAMETERS = ControllerParameters(
    start_velocity=10,
    stop_velocity=10,
    first_velocity=50,
    max_velocity=50,
    first_acceleration=120,
    max_acceleration=80,
    max_deceleration=80,
    first_deceleration=120,
)
SAFE_HOME_PARAMETERS = HomeParameters(
    travel_limit=100,
    max_velocity=10,
    run_current=43,
    stall_threshold=0,
)
DEFAULT_STALL_PLAUSIBILITY_TOLERANCE_MM = 2


def _default_log_file() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "logs" / f"researcher_workflow_stress_{timestamp}.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--cycle-count", type=int, default=10)
    parser.add_argument("--double-moves-per-cycle", type=int, default=3)
    parser.add_argument("--random-low", type=int, default=0)
    parser.add_argument("--random-high", type=int, default=120)
    parser.add_argument("--startup-home-repeat-count", type=int, default=5)
    parser.add_argument("--midday-rehome-every", type=int, default=5)
    parser.add_argument("--midday-home-repeat-count", type=int, default=2)
    parser.add_argument("--post-home-target", type=int, default=40)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--position-timeout", type=float, default=35.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=1)
    parser.add_argument(
        "--stall-plausibility-tolerance",
        type=int,
        default=DEFAULT_STALL_PLAUSIBILITY_TOLERANCE_MM,
    )
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument(
        "--no-confirm-after-startup-home",
        action="store_true",
        help=(
            "Do not issue confirm-home after the repeated untrusted startup homes. "
            "This is expected to leave firmware unhomed unless StallGuard gives a "
            "trusted home signal."
        ),
    )
    parser.add_argument("--log-file", type=Path, default=None)
    parser.add_argument("--no-log-file", action="store_true")
    parser.add_argument("--compact-output", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, HomeOutcome):
        return value.name
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def _write_event(log: TextIO | None, event: dict[str, object]) -> None:
    if log is None:
        return
    log.write(json.dumps(event, default=_json_default, sort_keys=True) + "\n")
    log.flush()


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


def _state_snapshot(hmi: HexMazeInterface, cluster_address: int) -> dict[str, object]:
    return {
        "cluster_address": cluster_address,
        "communicating": hmi.communicating_cluster(cluster_address),
        "controller_parameters": asdict(hmi.read_controller_parameters_cluster(cluster_address)),
        "home_outcomes": [
            outcome.name for outcome in hmi.read_home_outcomes_cluster(cluster_address)
        ],
        "homed": list(hmi.homed_cluster(cluster_address)),
        "positions_mm": list(hmi.read_positions_cluster(cluster_address)),
        "prism_diagnostics": _diagnostics_snapshot(hmi, cluster_address),
        "run_current_percent": hmi.read_run_current_cluster(cluster_address),
    }


def _best_effort_state_snapshot(
    hmi: HexMazeInterface,
    cluster_address: int,
) -> dict[str, object]:
    try:
        return _state_snapshot(hmi, cluster_address)
    except MazeException as exc:
        return {"cluster_address": cluster_address, "error": str(exc)}


def _verify_clean_terminal_state(snapshot: dict[str, object], context: str) -> None:
    if not snapshot["communicating"]:
        raise MazeException(f"{context}: cluster is not communicating")
    if not all(bool(value) for value in snapshot["homed"]):
        raise MazeException(f"{context}: expected all prisms homed: {snapshot}")
    diagnostics = snapshot["prism_diagnostics"]
    if isinstance(diagnostics, dict):
        raise MazeException(f"{context}: diagnostics read failed: {diagnostics}")
    fault_keys = (
        "charge_pump_undervoltage_latched",
        "communication_failure_latched",
        "driver_error_latched",
        "mirror_resync_required",
        "over_temperature_shutdown",
        "over_temperature_warning",
        "recovery_attempted_latched",
        "recovery_failed_latched",
        "reset_latched",
        "short_to_ground_a",
        "short_to_ground_b",
    )
    faults = [
        {"prism": prism_index, "fault": key}
        for prism_index, row in enumerate(diagnostics)
        for key in fault_keys
        if bool(row.get(key))
    ]
    if faults:
        raise MazeException(f"{context}: diagnostic faults detected: {faults}")


def _wait_for_positions(
    hmi: HexMazeInterface,
    cluster_address: int,
    targets_mm: tuple[int, ...],
    timeout_s: float,
    poll_interval_s: float,
    tolerance_mm: int,
) -> dict[str, object]:
    start = time.monotonic()
    deadline = start + timeout_s
    first_sample: dict[str, object] | None = None
    last_sample: dict[str, object] = {}
    while time.monotonic() < deadline:
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        sample = {
            "elapsed_s": round(time.monotonic() - start, 3),
            "positions_mm": list(positions),
        }
        if first_sample is None:
            first_sample = sample
        last_sample = sample
        if all(
            abs(position - target) <= tolerance_mm
            for position, target in zip(positions, targets_mm, strict=True)
        ):
            time.sleep(poll_interval_s)
            settled_positions = tuple(hmi.read_positions_cluster(cluster_address))
            return {
                "elapsed_s": round(time.monotonic() - start, 3),
                "final_positions_mm": list(settled_positions),
                "first_sample": first_sample,
                "last_sample": {
                    "elapsed_s": round(time.monotonic() - start, 3),
                    "positions_mm": list(settled_positions),
                },
            }
        time.sleep(poll_interval_s)
    raise MazeException(
        f"cluster {cluster_address} did not reach {list(targets_mm)}; "
        f"last state was {last_sample}"
    )


def _wait_for_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    start = time.monotonic()
    deadline = start + timeout_s
    first_sample: dict[str, object] | None = None
    last_sample: dict[str, object] = {}
    while time.monotonic() < deadline:
        homed = tuple(bool(value) for value in hmi.homed_cluster(cluster_address))
        outcomes = tuple(hmi.read_home_outcomes_cluster(cluster_address))
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        sample = {
            "elapsed_s": round(time.monotonic() - start, 3),
            "homed": list(homed),
            "outcomes": [outcome.name for outcome in outcomes],
            "positions_mm": list(positions),
        }
        if first_sample is None:
            first_sample = sample
        last_sample = sample
        if any(outcome == HomeOutcome.FAILED for outcome in outcomes):
            raise MazeException(f"home failed: {sample}")
        if all(outcome != HomeOutcome.IN_PROGRESS for outcome in outcomes):
            time.sleep(poll_interval_s)
            homed = tuple(bool(value) for value in hmi.homed_cluster(cluster_address))
            outcomes = tuple(hmi.read_home_outcomes_cluster(cluster_address))
            positions = tuple(hmi.read_positions_cluster(cluster_address))
            return {
                "elapsed_s": round(time.monotonic() - start, 3),
                "homed": list(homed),
                "outcomes": [outcome.name for outcome in outcomes],
                "positions_mm": list(positions),
                "first_sample": first_sample,
                "last_sample": last_sample,
            }
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish home; last={last_sample}")


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
        last_home_travel_mm = int(
            dict(diagnostic_rows[prism_index])["last_home_travel_mm"]
        )
        if last_home_travel_mm + tolerance_mm < expected_start_mm:
            affected.append(
                {
                    "prism": prism_index,
                    "before_position_mm": expected_start_mm,
                    "last_home_travel_mm": last_home_travel_mm,
                    "tolerance_mm": tolerance_mm,
                }
            )
    if affected:
        raise MazeException(f"{context}: implausible STALL outcome(s): {affected}")


def _write_controller_parameters(hmi: HexMazeInterface, cluster_address: int) -> None:
    if not hmi.write_controller_parameters_cluster(
        cluster_address, SAFE_CONTROLLER_PARAMETERS
    ):
        raise MazeException("write_controller_parameters_cluster failed")
    actual = hmi.read_controller_parameters_cluster(cluster_address)
    if actual.to_tuple() != SAFE_CONTROLLER_PARAMETERS.to_tuple():
        raise MazeException(
            "controller parameter readback mismatch: "
            f"expected={asdict(SAFE_CONTROLLER_PARAMETERS)}, actual={asdict(actual)}"
        )


def _random_targets(
    rng: random.Random,
    low: int,
    high: int,
) -> tuple[int, ...]:
    return tuple(rng.randint(low, high) for _ in range(HexMazeInterface.PRISM_COUNT))


def _clamp_position(position_mm: int, low: int, high: int) -> int:
    return max(low, min(high, position_mm))


def _masking_double_targets(
    rng: random.Random,
    current_positions: tuple[int, ...],
    low: int,
    high: int,
) -> tuple[tuple[int, int], ...]:
    final_targets = tuple(rng.randint(low, high) for _ in current_positions)
    pairs: list[tuple[int, int]] = []
    for current_position, final_target in zip(
        current_positions, final_targets, strict=True
    ):
        if current_position <= (low + high) // 2:
            mask_target = _clamp_position(current_position + 30, low, high)
        else:
            mask_target = _clamp_position(current_position - 30, low, high)
        if abs(mask_target - current_position) < 10:
            mask_target = rng.randint(low, high)
        pairs.append((mask_target, final_target))
    return tuple(pairs)


def _home_repeated(
    hmi: HexMazeInterface,
    cluster_address: int,
    repeat_count: int,
    timeout_s: float,
    poll_interval_s: float,
    stall_plausibility_tolerance_mm: int,
    log: TextIO | None,
    *,
    validate_stall: bool,
    context: str,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for index in range(repeat_count):
        before_positions = tuple(hmi.read_positions_cluster(cluster_address))
        _write_event(
            log,
            {
                "event": "home_start",
                "context": context,
                "index": index,
                "cluster_address": cluster_address,
                "before_positions_mm": list(before_positions),
                "home_parameters": asdict(SAFE_HOME_PARAMETERS),
                "validate_stall": validate_stall,
            },
        )
        if not hmi.home_cluster(cluster_address, SAFE_HOME_PARAMETERS):
            _write_event(
                log,
                {
                    "event": "home_start_failed",
                    "context": context,
                    "index": index,
                    "cluster_address": cluster_address,
                    "state": _best_effort_state_snapshot(hmi, cluster_address),
                },
            )
            raise MazeException(f"{context}: home {index} failed to start")
        try:
            report = _wait_for_home(hmi, cluster_address, timeout_s, poll_interval_s)
        except MazeException as exc:
            _write_event(
                log,
                {
                    "event": "home_failure",
                    "context": context,
                    "index": index,
                    "cluster_address": cluster_address,
                    "error": str(exc),
                    "state": _best_effort_state_snapshot(hmi, cluster_address),
                },
            )
            raise
        diagnostics = _diagnostics_snapshot(hmi, cluster_address)
        if validate_stall:
            try:
                _raise_on_implausible_stall(
                    report,
                    before_positions,
                    diagnostics,
                    tuple(range(HexMazeInterface.PRISM_COUNT)),
                    stall_plausibility_tolerance_mm,
                    f"{context} home {index}",
                )
            except MazeException as exc:
                _write_event(
                    log,
                    {
                        "event": "home_failure",
                        "context": context,
                        "index": index,
                        "cluster_address": cluster_address,
                        "error": str(exc),
                        "home": report,
                        "diagnostics": diagnostics,
                        "state": _best_effort_state_snapshot(hmi, cluster_address),
                    },
                )
                raise
        pass_report = {
            "index": index,
            "before_positions_mm": list(before_positions),
            "home": report,
            "diagnostics": diagnostics,
        }
        reports.append(pass_report)
        _write_event(
            log,
            {
                "event": "home_complete",
                "context": context,
                "cluster_address": cluster_address,
                "result": pass_report,
            },
        )
    return reports


def _startup_unknown_sequence(
    hmi: HexMazeInterface,
    cluster_address: int,
    rng: random.Random,
    args: argparse.Namespace,
    log: TextIO | None,
) -> dict[str, object]:
    stage_targets = _random_targets(rng, args.random_low, args.random_high)
    _write_event(
        log,
        {
            "event": "startup_stage_targets",
            "cluster_address": cluster_address,
            "targets_mm": list(stage_targets),
        },
    )
    if not hmi.write_targets_cluster(cluster_address, stage_targets):
        raise MazeException("startup staging write_targets_cluster failed")
    staged = _wait_for_positions(
        hmi,
        cluster_address,
        stage_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    _write_event(
        log,
        {
            "event": "startup_stage_complete",
            "cluster_address": cluster_address,
            "result": staged,
        },
    )
    if not hmi.power_off_cluster(cluster_address):
        raise MazeException("startup power_off_cluster failed")
    _write_event(log, {"event": "startup_power_off", "cluster_address": cluster_address})
    if not hmi.power_on_cluster(cluster_address):
        raise MazeException("startup power_on_cluster failed")
    _write_event(log, {"event": "startup_power_on", "cluster_address": cluster_address})
    _write_controller_parameters(hmi, cluster_address)
    before_home = _state_snapshot(hmi, cluster_address)
    _write_event(
        log,
        {
            "event": "startup_before_repeated_home",
            "cluster_address": cluster_address,
            "state": before_home,
        },
    )
    home_reports = _home_repeated(
        hmi,
        cluster_address,
        args.startup_home_repeat_count,
        args.home_timeout,
        args.poll_interval,
        args.stall_plausibility_tolerance,
        log,
        validate_stall=False,
        context="startup unknown",
    )
    after_repeated_home = _state_snapshot(hmi, cluster_address)
    _write_event(
        log,
        {
            "event": "startup_after_repeated_home",
            "cluster_address": cluster_address,
            "state": after_repeated_home,
        },
    )
    confirm_result = None
    after_confirm = None
    if not args.no_confirm_after_startup_home:
        confirm_result = hmi.confirm_home_cluster(cluster_address)
        if not confirm_result:
            raise MazeException("confirm_home_cluster failed after startup homes")
        after_confirm = _state_snapshot(hmi, cluster_address)
        _verify_clean_terminal_state(after_confirm, "after startup confirm")
    report = {
        "stage_targets_mm": list(stage_targets),
        "staged": staged,
        "before_home_after_power_cycle": before_home,
        "home_reports": home_reports,
        "after_repeated_home": after_repeated_home,
        "confirm_home_cluster": confirm_result,
        "after_confirm": after_confirm,
    }
    _write_event(log, {"event": "startup_unknown_sequence", "result": report})
    return report


def _run_double_move(
    hmi: HexMazeInterface,
    cluster_address: int,
    rng: random.Random,
    args: argparse.Namespace,
    cycle_index: int,
    move_index: int,
) -> dict[str, object]:
    before_positions = tuple(hmi.read_positions_cluster(cluster_address))
    double_targets = _masking_double_targets(
        rng, before_positions, args.random_low, args.random_high
    )
    final_targets = tuple(target for _, target in double_targets)
    if not hmi.write_double_targets_cluster(cluster_address, double_targets):
        raise MazeException(
            f"cycle {cycle_index} move {move_index}: write_double_targets_cluster failed"
        )
    movement = _wait_for_positions(
        hmi,
        cluster_address,
        final_targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    final_positions = tuple(int(value) for value in movement["final_positions_mm"])
    failed = [
        prism_index
        for prism_index, (position, target) in enumerate(
            zip(final_positions, final_targets, strict=True)
        )
        if abs(position - target) > args.position_tolerance
    ]
    if failed:
        raise MazeException(
            f"cycle {cycle_index} move {move_index}: final target mismatch: "
            f"failed={failed}, targets={list(final_targets)}, final={list(final_positions)}"
        )
    return {
        "cycle": cycle_index,
        "move": move_index,
        "before_positions_mm": list(before_positions),
        "double_targets_mm": [list(pair) for pair in double_targets],
        "final_targets_mm": list(final_targets),
        **movement,
    }


def _post_home_move(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
    context: str,
) -> dict[str, object]:
    targets = tuple(args.post_home_target for _ in range(HexMazeInterface.PRISM_COUNT))
    before_positions = tuple(hmi.read_positions_cluster(cluster_address))
    if not hmi.write_double_targets_cluster(
        cluster_address, tuple((args.post_home_target // 2, args.post_home_target) for _ in targets)
    ):
        raise MazeException(f"{context}: post-home double target write failed")
    movement = _wait_for_positions(
        hmi,
        cluster_address,
        targets,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    final_positions = tuple(int(value) for value in movement["final_positions_mm"])
    stationary = [
        prism_index
        for prism_index, (before, after) in enumerate(
            zip(before_positions, final_positions, strict=True)
        )
        if abs(after - before) <= args.position_tolerance
    ]
    if stationary:
        raise MazeException(
            f"{context}: stationary prism(s) after post-home move: {stationary}; "
            f"before={list(before_positions)}, final={list(final_positions)}"
        )
    return {
        "before_positions_mm": list(before_positions),
        "targets_mm": list(targets),
        "stationary_prisms": stationary,
        **movement,
    }


def _run_cycle(
    hmi: HexMazeInterface,
    cluster_address: int,
    rng: random.Random,
    args: argparse.Namespace,
    cycle_index: int,
    log: TextIO | None,
) -> dict[str, object]:
    moves: list[dict[str, object]] = []
    for move_index in range(args.double_moves_per_cycle):
        move = _run_double_move(hmi, cluster_address, rng, args, cycle_index, move_index)
        moves.append(move)
        _write_event(log, {"event": "cycle_move_success", "result": move})
    rehome = None
    post_rehome_move = None
    if (
        args.midday_rehome_every > 0
        and (cycle_index + 1) % args.midday_rehome_every == 0
    ):
        rehome = _home_repeated(
            hmi,
            cluster_address,
            args.midday_home_repeat_count,
            args.home_timeout,
            args.poll_interval,
            args.stall_plausibility_tolerance,
            log,
            validate_stall=True,
            context=f"cycle {cycle_index} midday rehome",
        )
        after_rehome = _state_snapshot(hmi, cluster_address)
        _verify_clean_terminal_state(after_rehome, f"cycle {cycle_index} after rehome")
        post_rehome_move = _post_home_move(
            hmi, cluster_address, args, f"cycle {cycle_index} post-rehome"
        )
    snapshot = _state_snapshot(hmi, cluster_address)
    _verify_clean_terminal_state(snapshot, f"cycle {cycle_index} final")
    report = {
        "cycle": cycle_index,
        "moves": moves,
        "rehome": rehome,
        "post_rehome_move": post_rehome_move,
        "final_snapshot": snapshot,
    }
    _write_event(log, {"event": "cycle_success", **report})
    return report


def _validate_args(args: argparse.Namespace) -> None:
    if args.cycle_count <= 0:
        raise MazeException("--cycle-count must be positive")
    if args.double_moves_per_cycle <= 0:
        raise MazeException("--double-moves-per-cycle must be positive")
    if args.random_low < 0 or args.random_high > 550:
        raise MazeException("--random-low/--random-high must stay within 0..550")
    if args.random_low >= args.random_high:
        raise MazeException("--random-low must be less than --random-high")
    if args.startup_home_repeat_count <= 0:
        raise MazeException("--startup-home-repeat-count must be positive")
    if args.midday_home_repeat_count <= 0:
        raise MazeException("--midday-home-repeat-count must be positive")
    if args.stall_plausibility_tolerance < 0:
        raise MazeException("--stall-plausibility-tolerance must be non-negative")
    if args.post_home_target < 0 or args.post_home_target > 550:
        raise MazeException("--post-home-target must stay within 0..550")


def _compact_summary(result: dict[str, object]) -> dict[str, object]:
    cycles = list(result["cycles"])
    return {
        "cluster": result["cluster"],
        "ok": result["ok"],
        "cycle_count": len(cycles),
        "double_move_count": sum(len(dict(cycle)["moves"]) for cycle in cycles),
        "midday_rehome_count": sum(1 for cycle in cycles if dict(cycle)["rehome"]),
        "log_file": result["log_file"],
        "final_positions_mm": result["final_snapshot"]["positions_mm"],
        "finished_at": result["finished_at"],
    }


def main() -> int:
    args = _parse_args()
    _validate_args(args)
    rng = random.Random(args.seed)
    log_file = None if args.no_log_file else (args.log_file or _default_log_file())
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now().isoformat(timespec="seconds")
    result: dict[str, object] = {
        "cluster": args.cluster,
        "started_at": started_at,
        "log_file": str(log_file) if log_file is not None else None,
        "parameters": {
            "controller": asdict(SAFE_CONTROLLER_PARAMETERS),
            "home": asdict(SAFE_HOME_PARAMETERS),
            "cycle_count": args.cycle_count,
            "double_moves_per_cycle": args.double_moves_per_cycle,
            "startup_home_repeat_count": args.startup_home_repeat_count,
            "midday_rehome_every": args.midday_rehome_every,
            "midday_home_repeat_count": args.midday_home_repeat_count,
            "random_low": args.random_low,
            "random_high": args.random_high,
        },
        "ok": False,
    }

    try:
        log_context = (
            log_file.open("w", encoding="utf-8")
            if log_file is not None
            else nullcontext(None)
        )
        with log_context as log:
            _write_event(log, {"event": "run_start", **result})
            with HexMazeInterface(debug=args.debug) as hmi:
                if not hmi.verify_cluster(args.cluster)["checks"].get(
                    "communicating", False
                ):
                    raise MazeException(f"cluster {args.cluster} is not communicating")
                _write_controller_parameters(hmi, args.cluster)
                if not all(bool(value) for value in hmi.homed_cluster(args.cluster)):
                    raise MazeException(
                        "cluster must start from a trusted homed baseline; "
                        "visually home and confirm it before running this workflow test"
                    )
                startup = _startup_unknown_sequence(hmi, args.cluster, rng, args, log)
                post_startup_move = _post_home_move(
                    hmi, args.cluster, args, "post-startup"
                )
                cycles = [
                    _run_cycle(hmi, args.cluster, rng, args, cycle_index, log)
                    for cycle_index in range(args.cycle_count)
                ]
                final_snapshot = _state_snapshot(hmi, args.cluster)
                _verify_clean_terminal_state(final_snapshot, "final")
            result.update(
                {
                    "startup": startup,
                    "post_startup_move": post_startup_move,
                    "cycles": cycles,
                    "final_snapshot": final_snapshot,
                    "ok": True,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            _write_event(log, {"event": "run_success", **result})
    except MazeException as exc:
        result.update(
            {
                "error": str(exc),
                "ok": False,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if log_file is not None:
            with log_file.open("a", encoding="utf-8") as log:
                _write_event(log, {"event": "run_failure", **result})
        print(json.dumps(result, default=_json_default, indent=2, sort_keys=True))
        return 1

    output = _compact_summary(result) if args.compact_output else result
    print(json.dumps(output, default=_json_default, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
