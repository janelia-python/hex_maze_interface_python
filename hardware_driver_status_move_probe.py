#!/usr/bin/env python3
"""Sample live TMC driver status during a quiet normal cluster move."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from hex_maze_interface import HexMazeInterface, MazeException


def _default_log_file() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "logs" / f"driver_status_move_probe_{timestamp}.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--return-target", type=int)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    parser.add_argument("--position-tolerance", type=int, default=1)
    parser.add_argument("--max-flag-samples", type=int, default=5)
    parser.add_argument("--log-file", type=Path, default=_default_log_file())
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _diagnostic_flags(diagnostics: dict[str, Any]) -> list[str]:
    return [
        name
        for name in (
            "short_to_ground_a",
            "short_to_ground_b",
            "open_load_a",
            "open_load_b",
            "driver_error_latched",
            "reset_latched",
            "charge_pump_undervoltage_latched",
            "over_temperature_warning",
            "over_temperature_shutdown",
        )
        if diagnostics.get(name, False)
    ]


def _target_reached(
    positions: tuple[int, ...],
    targets: tuple[int, ...],
    tolerance: int,
) -> bool:
    return all(
        abs(position - target) <= tolerance
        for position, target in zip(positions, targets, strict=True)
    )


def _sample_move(
    hmi: HexMazeInterface,
    cluster_address: int,
    target: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    targets = (target,) * hmi.PRISM_COUNT
    start_positions = tuple(hmi.read_positions_cluster(cluster_address))
    if not hmi.clear_prism_diagnostics_cluster(cluster_address):
        raise MazeException("clear_prism_diagnostics_cluster failed")
    if not hmi.write_targets_cluster(cluster_address, targets):
        raise MazeException("write_targets_cluster failed")

    samples: list[dict[str, Any]] = []
    start = time.monotonic()
    deadline = start + args.timeout
    while time.monotonic() < deadline:
        elapsed_s = time.monotonic() - start
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        diagnostics = [
            asdict(diagnostic) for diagnostic in hmi.read_prism_diagnostics_cluster(cluster_address)
        ]
        samples.append(
            {
                "elapsed_s": round(elapsed_s, 3),
                "positions_mm": list(positions),
                "diagnostics": diagnostics,
            }
        )
        if _target_reached(positions, targets, args.position_tolerance):
            time.sleep(args.poll_interval)
            break
        time.sleep(args.poll_interval)

    final_positions = tuple(hmi.read_positions_cluster(cluster_address))
    final_diagnostics = [
        asdict(diagnostic) for diagnostic in hmi.read_prism_diagnostics_cluster(cluster_address)
    ]

    per_prism: list[dict[str, Any]] = []
    for prism_index in range(hmi.PRISM_COUNT):
        energized_samples = 0
        moving_or_energized_flag_samples: list[dict[str, Any]] = []
        standstill_flag_samples: list[dict[str, Any]] = []
        max_current_scale = 0
        for sample in samples:
            diagnostic = sample["diagnostics"][prism_index]
            flags = _diagnostic_flags(diagnostic)
            current_scale = int(diagnostic["current_scale"])
            max_current_scale = max(max_current_scale, current_scale)
            energized = current_scale > 0 or not diagnostic["standstill"]
            if energized:
                energized_samples += 1
            if not flags:
                continue
            flag_sample = {
                "elapsed_s": sample["elapsed_s"],
                "flags": flags,
                "current_scale": current_scale,
                "standstill": diagnostic["standstill"],
                "position_mm": sample["positions_mm"][prism_index],
            }
            if energized:
                moving_or_energized_flag_samples.append(flag_sample)
            else:
                standstill_flag_samples.append(flag_sample)

        per_prism.append(
            {
                "prism": prism_index,
                "start_position_mm": start_positions[prism_index],
                "final_position_mm": final_positions[prism_index],
                "max_current_scale": max_current_scale,
                "energized_sample_count": energized_samples,
                "energized_flag_sample_count": len(moving_or_energized_flag_samples),
                "energized_flag_samples": moving_or_energized_flag_samples[: args.max_flag_samples],
                "standstill_flag_sample_count": len(standstill_flag_samples),
                "standstill_flag_samples": standstill_flag_samples[: args.max_flag_samples],
                "final_diagnostics": final_diagnostics[prism_index],
            }
        )

    return {
        "event": "driver_status_move_probe",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cluster": cluster_address,
        "target_mm": target,
        "start_positions_mm": list(start_positions),
        "final_positions_mm": list(final_positions),
        "sample_count": len(samples),
        "per_prism": per_prism,
    }


def main() -> int:
    args = _parse_args()
    args.log_file.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with HexMazeInterface(debug=args.debug) as hmi:
        if not hmi.communicating_cluster(args.cluster):
            raise MazeException(f"cluster {args.cluster} failed communication check")

        results.append(_sample_move(hmi, args.cluster, args.target, args))
        if args.return_target is not None:
            results.append(_sample_move(hmi, args.cluster, args.return_target, args))

    with args.log_file.open("a", encoding="utf-8") as log:
        for result in results:
            print(json.dumps(result, sort_keys=True))
            log.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MazeException as exc:
        print(json.dumps({"event": "error", "error": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
