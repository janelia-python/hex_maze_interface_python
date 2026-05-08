#!/usr/bin/env python3
"""Check whether duplicate target writes cause unintended positive motion."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TextIO

from hex_maze_interface import ControllerParameters, HexMazeInterface, HomeOutcome, MazeException

SAFE_START_STOP_MAX_MM_S = 10
SAFE_STOP_MIN_MM_S = 10


def _default_log_file() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "logs" / f"duplicate_target_regression_{timestamp}.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=int, nargs="+", required=True)
    parser.add_argument(
        "--protocol-version",
        type=lambda value: int(value, 0),
        choices=(0x04, 0x06),
        default=HexMazeInterface.PROTOCOL_VERSION,
        help="Firmware protocol to speak. Use 0x04 before flashing old full-rig firmware.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only read communication, homed state, positions, and controller parameters.",
    )
    parser.add_argument(
        "--controller-only",
        action="store_true",
        help="Write and verify controller parameters without issuing target writes.",
    )
    parser.add_argument(
        "--require-homed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require all prisms in each cluster to report homed before target writes.",
    )
    parser.add_argument("--start-velocity", type=int, default=20)
    parser.add_argument("--stop-velocity", type=int, default=20)
    parser.add_argument("--first-velocity", type=int, default=40)
    parser.add_argument("--max-velocity", type=int, default=40)
    parser.add_argument("--first-acceleration", type=int, default=120)
    parser.add_argument("--max-acceleration", type=int, default=80)
    parser.add_argument("--max-deceleration", type=int, default=80)
    parser.add_argument("--first-deceleration", type=int, default=120)
    parser.add_argument(
        "--allow-aggressive-motion-settings",
        action="store_true",
        help=(
            "Allow requested start/stop velocity outside the safe ramp profile "
            "for supervised reproductions."
        ),
    )
    parser.add_argument(
        "--allow-clamped-controller-readback",
        action="store_true",
        help="Allow readback to differ from requested values when validating firmware clamps.",
    )
    parser.add_argument(
        "--require-safe-start-stop-readback",
        action="store_true",
        help=(
            "Fail unless controller readback has start <= 10 mm/s, "
            "stop == 10 mm/s, and stop >= start."
        ),
    )
    parser.add_argument("--target-base", type=int, default=40)
    parser.add_argument("--target-step", type=int, default=5)
    parser.add_argument("--cluster-target-offset", type=int, default=0)
    parser.add_argument(
        "--resume-before-motion",
        action="store_true",
        help="Resume the cluster after controller writes and before target writes.",
    )
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--pre-duplicate-settle", type=float, default=1.0)
    parser.add_argument("--duplicate-observation", type=float, default=4.0)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--drift-tolerance", type=int, default=5)
    parser.add_argument(
        "--pause-on-failure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pause an affected cluster after a timeout or duplicate-target drift.",
    )
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="Continue with later clusters after a failure. Default is to stop immediately.",
    )
    parser.add_argument("--log-file", type=Path, default=None)
    parser.add_argument("--compact-output", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _controller_parameters_from_args(args: argparse.Namespace) -> ControllerParameters:
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


def _home_outcome_names(hmi: HexMazeInterface, cluster_address: int) -> list[str]:
    try:
        outcomes = hmi.read_home_outcomes_cluster(cluster_address)
    except (MazeException, ValueError) as exc:
        return [f"unavailable: {exc}"]
    names: list[str] = []
    for outcome in outcomes:
        try:
            names.append(HomeOutcome(outcome).name)
        except ValueError:
            names.append(f"UNKNOWN_{int(outcome)}")
    return names


def _cluster_state(
    hmi: HexMazeInterface,
    cluster_address: int,
    *,
    include_diagnostics: bool,
) -> dict[str, object]:
    communicating = hmi.communicating_cluster(cluster_address)
    report: dict[str, object] = {
        "cluster": cluster_address,
        "communicating": communicating,
    }
    if not communicating:
        return report

    report["homed"] = list(hmi.homed_cluster(cluster_address))
    report["home_outcomes"] = _home_outcome_names(hmi, cluster_address)
    report["positions_mm"] = list(hmi.read_positions_cluster(cluster_address))
    report["controller_parameters"] = asdict(
        hmi.read_controller_parameters_cluster(cluster_address)
    )
    report["run_current_percent"] = hmi.read_run_current_cluster(cluster_address)
    if include_diagnostics:
        report["prism_diagnostics"] = [
            asdict(diagnostic) for diagnostic in hmi.read_prism_diagnostics_cluster(cluster_address)
        ]
    return report


def _targets_for_cluster(cluster_index: int, args: argparse.Namespace) -> tuple[int, ...]:
    base = args.target_base + cluster_index * args.cluster_target_offset
    targets = tuple(
        base + prism_index * args.target_step for prism_index in range(hmi_prism_count())
    )
    invalid = [
        target
        for target in targets
        if target < HexMazeInterface.POSITION_MIN_MM or target > HexMazeInterface.POSITION_MAX_MM
    ]
    if invalid:
        raise MazeException(f"generated target outside 0..550 mm: {invalid}")
    return targets


def hmi_prism_count() -> int:
    return HexMazeInterface.PRISM_COUNT


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


def _write_jsonl(log: TextIO, record: dict[str, object]) -> None:
    print(json.dumps(record, sort_keys=True), file=log, flush=True)


def _write_controller_parameters(
    hmi: HexMazeInterface,
    cluster_address: int,
    requested: ControllerParameters,
    args: argparse.Namespace,
) -> dict[str, object]:
    before = hmi.read_controller_parameters_cluster(cluster_address)
    if not hmi.write_controller_parameters_cluster(cluster_address, requested):
        raise MazeException(f"cluster {cluster_address} controller parameter write failed")
    after = hmi.read_controller_parameters_cluster(cluster_address)

    if not args.allow_clamped_controller_readback and after.to_tuple() != requested.to_tuple():
        raise MazeException(
            f"cluster {cluster_address} controller readback mismatch: "
            f"requested {requested.to_tuple()}, got {after.to_tuple()}"
        )

    if args.require_safe_start_stop_readback and (
        after.start_velocity > SAFE_START_STOP_MAX_MM_S
        or after.stop_velocity > SAFE_START_STOP_MAX_MM_S
        or after.stop_velocity < SAFE_STOP_MIN_MM_S
        or after.stop_velocity < after.start_velocity
    ):
        raise MazeException(
            f"cluster {cluster_address} accepted unsafe start/stop readback: "
            f"{after.start_velocity}/{after.stop_velocity}"
        )

    return {
        "before": asdict(before),
        "requested": asdict(requested),
        "after": asdict(after),
    }


def _monitor_duplicate_target(
    hmi: HexMazeInterface,
    cluster_address: int,
    baseline_positions: tuple[int, ...],
    targets_mm: tuple[int, ...],
    args: argparse.Namespace,
) -> dict[str, object]:
    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        raise MazeException(f"cluster {cluster_address} duplicate write_targets_cluster failed")

    start_time = time.monotonic()
    deadline = start_time + args.duplicate_observation
    samples: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        deltas = tuple(
            position - baseline
            for position, baseline in zip(positions, baseline_positions, strict=True)
        )
        samples.append(
            {
                "elapsed_s": round(time.monotonic() - start_time, 3),
                "positions_mm": list(positions),
                "delta_mm": list(deltas),
            }
        )
        time.sleep(args.poll_interval)

    max_positive_drift = [
        max(sample["delta_mm"][index] for sample in samples) for index in range(hmi_prism_count())
    ]
    max_absolute_drift = [
        max(abs(sample["delta_mm"][index]) for sample in samples)
        for index in range(hmi_prism_count())
    ]
    positive_drift_prisms = [
        index for index, drift in enumerate(max_positive_drift) if drift > args.drift_tolerance
    ]
    drift_prisms = [
        index for index, drift in enumerate(max_absolute_drift) if drift > args.drift_tolerance
    ]

    status = "stable"
    if positive_drift_prisms:
        status = "positive_drift"
    elif drift_prisms:
        status = "drift"

    return {
        "status": status,
        "targets_mm": list(targets_mm),
        "baseline_positions_mm": list(baseline_positions),
        "max_positive_drift_mm": max_positive_drift,
        "max_absolute_drift_mm": max_absolute_drift,
        "positive_drift_prisms": positive_drift_prisms,
        "drift_prisms": drift_prisms,
        "samples": samples,
    }


def _run_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    cluster_index: int,
    requested_controller: ControllerParameters,
    args: argparse.Namespace,
) -> dict[str, object]:
    include_diagnostics = args.protocol_version >= 0x06
    initial_state = _cluster_state(hmi, cluster_address, include_diagnostics=include_diagnostics)
    if not initial_state["communicating"]:
        raise MazeException(f"cluster {cluster_address} is not communicating")

    if args.read_only:
        return {
            "event": "cluster_read_only",
            "cluster": cluster_address,
            "protocol_version": args.protocol_version,
            "state": initial_state,
        }

    if args.controller_only:
        controller_report = _write_controller_parameters(
            hmi,
            cluster_address,
            requested_controller,
            args,
        )
        final_state = _cluster_state(hmi, cluster_address, include_diagnostics=include_diagnostics)
        return {
            "event": "cluster_controller_only",
            "cluster": cluster_address,
            "protocol_version": args.protocol_version,
            "status": "stable",
            "initial_state": initial_state,
            "controller_parameters": controller_report,
            "final_state": final_state,
        }

    if args.require_homed and not all(initial_state.get("homed", [])):
        raise MazeException(f"cluster {cluster_address} is not fully homed: {initial_state}")

    controller_report = _write_controller_parameters(
        hmi,
        cluster_address,
        requested_controller,
        args,
    )
    if args.resume_before_motion and not hmi.resume_cluster(cluster_address):
        raise MazeException(f"cluster {cluster_address} resume_cluster failed")
    targets_mm = _targets_for_cluster(cluster_index, args)

    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        raise MazeException(f"cluster {cluster_address} write_targets_cluster failed")
    reached_positions = _wait_for_positions(
        hmi,
        cluster_address,
        targets_mm,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    time.sleep(args.pre_duplicate_settle)
    baseline_positions = tuple(hmi.read_positions_cluster(cluster_address))
    duplicate_report = _monitor_duplicate_target(
        hmi,
        cluster_address,
        baseline_positions,
        targets_mm,
        args,
    )
    final_state = _cluster_state(hmi, cluster_address, include_diagnostics=include_diagnostics)

    return {
        "event": "cluster_duplicate_target_probe",
        "cluster": cluster_address,
        "protocol_version": args.protocol_version,
        "status": duplicate_report["status"],
        "initial_state": initial_state,
        "controller_parameters": controller_report,
        "first_target_reached_positions_mm": list(reached_positions),
        "duplicate_target": duplicate_report,
        "final_state": final_state,
    }


def _pause_after_failure(
    hmi: HexMazeInterface,
    cluster_address: int,
    error: BaseException | None,
) -> dict[str, object]:
    try:
        paused = hmi.pause_cluster(cluster_address)
    except MazeException as exc:
        return {"attempted": True, "ok": False, "error": str(exc), "trigger": str(error)}
    return {"attempted": True, "ok": paused, "trigger": str(error)}


def _print_record(record: dict[str, object], compact: bool) -> None:
    if compact:
        print(json.dumps(record, sort_keys=True))
    else:
        print(json.dumps(record, indent=2, sort_keys=True))


def main() -> int:
    args = _parse_args()
    requested_controller = _controller_parameters_from_args(args)
    requested_unsafe_ramp_profile = (
        requested_controller.start_velocity > SAFE_START_STOP_MAX_MM_S
        or requested_controller.stop_velocity > SAFE_START_STOP_MAX_MM_S
        or requested_controller.stop_velocity < SAFE_STOP_MIN_MM_S
        or requested_controller.stop_velocity < requested_controller.start_velocity
    )
    if (
        not args.read_only
        and not args.allow_aggressive_motion_settings
        and requested_unsafe_ramp_profile
    ):
        raise MazeException(
            "requested start/stop velocity is outside the safe ramp profile "
            "(start <= 10 mm/s, stop == 10 mm/s, stop >= start); rerun with "
            "--allow-aggressive-motion-settings for a supervised reproduction"
        )

    HexMazeInterface.PROTOCOL_VERSION = args.protocol_version
    log_file = args.log_file or _default_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    ok = True

    with log_file.open("a", encoding="utf-8") as log, HexMazeInterface(debug=args.debug) as hmi:
        header = {
            "event": "duplicate_target_regression_start",
            "log_file": str(log_file),
            "protocol_version": args.protocol_version,
            "clusters": args.clusters,
            "requested_controller_parameters": asdict(requested_controller),
            "read_only": args.read_only,
        }
        _write_jsonl(log, header)
        print(f"log_file={log_file}")

        for cluster_index, cluster_address in enumerate(args.clusters):
            error: BaseException | None = None
            try:
                record = _run_cluster(
                    hmi,
                    cluster_address,
                    cluster_index,
                    requested_controller,
                    args,
                )
                if record.get("status") not in (None, "stable"):
                    ok = False
                    error = MazeException(f"cluster {cluster_address} status {record['status']}")
                    if args.pause_on_failure:
                        record["pause_after_failure"] = _pause_after_failure(
                            hmi,
                            cluster_address,
                            error,
                        )
            except (MazeException, OSError, TimeoutError, ValueError) as exc:
                ok = False
                error = exc
                record = {
                    "event": "cluster_duplicate_target_probe_error",
                    "cluster": cluster_address,
                    "protocol_version": args.protocol_version,
                    "error": str(exc),
                }
                try:
                    record["state_after_error"] = _cluster_state(
                        hmi,
                        cluster_address,
                        include_diagnostics=args.protocol_version >= 0x06,
                    )
                except (MazeException, OSError, TimeoutError, ValueError) as state_exc:
                    record["state_after_error"] = {"error": str(state_exc)}
                if args.pause_on_failure and not args.read_only:
                    record["pause_after_failure"] = _pause_after_failure(
                        hmi,
                        cluster_address,
                        error,
                    )

            _write_jsonl(log, record)
            _print_record(record, args.compact_output)

            if error is not None and not args.continue_after_failure:
                break

    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MazeException as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
