#!/usr/bin/env python3
"""Measure relative microphone noise during live homing trials."""

from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from hex_maze_interface import (
    HexMazeInterface,
    HomeOutcome,
    HomeParameters,
    MazeException,
)

DEFAULT_PROFILE = "quiet100:100:10:43:0"


@dataclass(frozen=True, slots=True)
class HomeNoiseProfile:
    name: str
    travel_limit: int
    max_velocity: int
    run_current: int
    stall_threshold: int

    def home_parameters(self) -> HomeParameters:
        return HomeParameters(
            travel_limit=self.travel_limit,
            max_velocity=self.max_velocity,
            run_current=self.run_current,
            stall_threshold=self.stall_threshold,
        )


def _default_log_file() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "logs" / f"home_noise_sweep_{timestamp}.jsonl"


def _parse_profile(value: str) -> HomeNoiseProfile:
    parts = value.split(":")
    if len(parts) != 5:
        raise argparse.ArgumentTypeError(
            "profile must be name:travel_limit:max_velocity:run_current:stall_threshold"
        )
    name, travel_limit, max_velocity, run_current, stall_threshold = parts
    try:
        return HomeNoiseProfile(
            name=name,
            travel_limit=int(travel_limit.removeprefix("v")),
            max_velocity=int(max_velocity),
            run_current=int(run_current),
            stall_threshold=int(stall_threshold),
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid numeric profile field: {value}") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", type=int, required=True)
    parser.add_argument(
        "--scope",
        choices=("prism", "cluster"),
        default="prism",
        help="Home one prism per trial or all seven prisms together.",
    )
    parser.add_argument("--prism", type=int, default=0)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--pre-home-position", type=int, default=40)
    parser.add_argument("--profile", action="append", type=_parse_profile)
    parser.add_argument("--audio-device", default="pulse")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--pre-roll", type=float, default=0.5)
    parser.add_argument("--post-roll", type=float, default=0.5)
    parser.add_argument("--record-seconds", type=float, default=0.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=1)
    parser.add_argument("--settle-seconds", type=float, default=0.5)
    parser.add_argument("--pause-between", type=float, default=1.0)
    parser.add_argument("--ambient-seconds", type=float, default=2.0)
    parser.add_argument("--output-log", type=Path, default=_default_log_file())
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "logs" / "audio",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(value, 1.0) / 32768.0)


def _segment_stats(samples: tuple[int, ...], sample_rate: int) -> dict[str, float | int]:
    if not samples:
        return {
            "sample_count": 0,
            "duration_s": 0.0,
            "rms_dbfs": -90.31,
            "peak_dbfs": -90.31,
            "p95_abs_dbfs": -90.31,
            "relative_exposure_db": -90.31,
        }
    abs_samples = [abs(sample) for sample in samples]
    peak = max(abs_samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    p95_index = min(len(abs_samples) - 1, int(len(abs_samples) * 0.95))
    p95 = sorted(abs_samples)[p95_index]
    rms_dbfs = _dbfs(rms)
    duration_s = len(samples) / sample_rate
    return {
        "sample_count": len(samples),
        "duration_s": round(duration_s, 3),
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(_dbfs(peak), 2),
        "p95_abs_dbfs": round(_dbfs(p95), 2),
        "relative_exposure_db": round(rms_dbfs + 10.0 * math.log10(max(duration_s, 1e-9)), 2),
    }


def _read_wav_samples(path: Path) -> tuple[int, tuple[int, ...]]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise MazeException(f"expected 16-bit WAV, got sample width {sample_width}")
    values = struct.unpack(f"<{len(frames) // 2}h", frames)
    if channels == 1:
        return sample_rate, values
    mono = tuple(
        round(sum(values[index : index + channels]) / channels)
        for index in range(0, len(values), channels)
    )
    return sample_rate, mono


def _analyze_wav(
    path: Path,
    active_start_s: float | None = None,
    active_end_s: float | None = None,
) -> dict[str, Any]:
    sample_rate, samples = _read_wav_samples(path)
    result: dict[str, Any] = {
        "sample_rate_hz": sample_rate,
        "full": _segment_stats(samples, sample_rate),
    }
    if active_start_s is not None and active_end_s is not None:
        start_index = max(0, int(active_start_s * sample_rate))
        end_index = min(len(samples), int(active_end_s * sample_rate))
        result["active"] = _segment_stats(samples[start_index:end_index], sample_rate)
        result["active_window_s"] = [round(active_start_s, 3), round(active_end_s, 3)]
    return result


def _record_wav(path: Path, args: argparse.Namespace, seconds: float) -> subprocess.Popen[bytes]:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "arecord",
        "-D",
        args.audio_device,
        "-f",
        "S16_LE",
        "-c",
        str(args.channels),
        "-r",
        str(args.sample_rate),
        "-d",
        str(max(1, math.ceil(seconds))),
        str(path),
    ]
    if args.debug:
        print("record:", " ".join(command))
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


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
        f"cluster {cluster_address} did not reach {list(targets_mm)}; "
        f"last positions were {list(last_positions)}"
    )


def _wait_for_home(
    hmi: HexMazeInterface,
    cluster_address: int,
    scope: str,
    prism_address: int,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        homed = tuple(bool(value) for value in hmi.homed_cluster(cluster_address))
        outcomes = tuple(hmi.read_home_outcomes_cluster(cluster_address))
        positions = tuple(hmi.read_positions_cluster(cluster_address))
        last = {
            "homed": list(homed),
            "outcomes": [outcome.name.lower() for outcome in outcomes],
            "positions_mm": list(positions),
        }
        selected = outcomes if scope == "cluster" else (outcomes[prism_address],)
        if all(outcome != HomeOutcome.IN_PROGRESS for outcome in selected):
            return last
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish homing; last={last}")


def _diagnostics_summary(hmi: HexMazeInterface, cluster_address: int) -> list[dict[str, Any]]:
    return [
        asdict(diagnostics) for diagnostics in hmi.read_prism_diagnostics_cluster(cluster_address)
    ]


def _prepare_position(
    hmi: HexMazeInterface,
    cluster_address: int,
    args: argparse.Namespace,
) -> tuple[int, ...]:
    target = args.pre_home_position
    if args.scope == "cluster":
        targets = (target,) * hmi.PRISM_COUNT
        if not hmi.write_targets_cluster(cluster_address, targets):
            raise MazeException("write_targets_cluster failed")
        _wait_for_positions(
            hmi,
            cluster_address,
            targets,
            args.position_timeout,
            args.poll_interval,
            args.position_tolerance,
        )
    else:
        if not hmi.write_target_prism(cluster_address, args.prism, target):
            raise MazeException(f"write_target_prism {args.prism} failed")
        current_targets = list(hmi.read_positions_cluster(cluster_address))
        current_targets[args.prism] = target
        targets = tuple(current_targets)
        _wait_for_positions(
            hmi,
            cluster_address,
            targets,
            args.position_timeout,
            args.poll_interval,
            args.position_tolerance,
        )

    if args.settle_seconds > 0:
        time.sleep(args.settle_seconds)
    settled_positions = tuple(hmi.read_positions_cluster(cluster_address))
    if not all(
        abs(position - target_position) <= args.position_tolerance
        for position, target_position in zip(settled_positions, targets, strict=True)
    ):
        raise MazeException(
            f"cluster {cluster_address} did not settle at {list(targets)}; "
            f"settled positions were {list(settled_positions)}"
        )
    return settled_positions


def _run_trial(
    hmi: HexMazeInterface,
    cluster_address: int,
    profile: HomeNoiseProfile,
    trial_index: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    prepared_positions = _prepare_position(hmi, cluster_address, args)
    if not hmi.clear_prism_diagnostics_cluster(cluster_address):
        raise MazeException("clear_prism_diagnostics_cluster failed")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = args.audio_dir / f"home_noise_{timestamp}_{profile.name}_{trial_index}.wav"
    record_seconds = args.record_seconds or (args.home_timeout + args.pre_roll + args.post_roll)
    recorder = _record_wav(wav_path, args, record_seconds)
    record_start = time.monotonic()
    time.sleep(args.pre_roll)
    command_start = time.monotonic()

    home_parameters = profile.home_parameters()
    if args.scope == "cluster":
        ok = hmi.home_cluster(cluster_address, home_parameters)
    else:
        ok = hmi.home_prism(cluster_address, args.prism, home_parameters)
    if not ok:
        raise MazeException("home command failed")

    home_report = _wait_for_home(
        hmi,
        cluster_address,
        args.scope,
        args.prism,
        args.home_timeout,
        args.poll_interval,
    )
    command_done = time.monotonic()
    active_start_s = max(0.0, command_start - record_start)
    active_end_s = command_done - record_start
    remaining_record_s = record_seconds - (time.monotonic() - record_start)
    if remaining_record_s > 0:
        time.sleep(remaining_record_s)
    stdout, stderr = recorder.communicate(timeout=5)
    if args.debug and (stdout or stderr):
        print(stdout.decode(errors="replace"), stderr.decode(errors="replace"))
    if recorder.returncode not in (0, None):
        raise MazeException(f"arecord failed with exit code {recorder.returncode}")

    audio = _analyze_wav(wav_path, active_start_s, active_end_s)
    diagnostics = _diagnostics_summary(hmi, cluster_address)
    return {
        "event": "home_noise_trial",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cluster": cluster_address,
        "scope": args.scope,
        "prism": args.prism if args.scope == "prism" else None,
        "trial": trial_index,
        "profile": asdict(profile),
        "prepared_positions_mm": list(prepared_positions),
        "home_report": home_report,
        "diagnostics": diagnostics,
        "audio": audio,
        "wav_path": str(wav_path),
    }


def _record_ambient(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = args.audio_dir / f"home_noise_ambient_{timestamp}.wav"
    recorder = _record_wav(wav_path, args, args.ambient_seconds)
    stdout, stderr = recorder.communicate(timeout=math.ceil(args.ambient_seconds) + 5)
    if args.debug and (stdout or stderr):
        print(stdout.decode(errors="replace"), stderr.decode(errors="replace"))
    if recorder.returncode != 0:
        raise MazeException(f"ambient arecord failed with exit code {recorder.returncode}")
    return {
        "event": "ambient_noise",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "audio": _analyze_wav(wav_path),
        "wav_path": str(wav_path),
    }


def main() -> int:
    args = _parse_args()
    profiles = args.profile or [_parse_profile(DEFAULT_PROFILE)]
    args.output_log.parent.mkdir(parents=True, exist_ok=True)

    with HexMazeInterface(debug=args.debug) as hmi:
        verify = hmi.verify_cluster(args.cluster)
        if not verify["checks"].get("communicating", False):
            raise MazeException(f"cluster {args.cluster} failed communication check")

        with args.output_log.open("a", encoding="utf-8") as log:
            if args.ambient_seconds > 0:
                ambient = _record_ambient(args)
                print(json.dumps(ambient, sort_keys=True))
                log.write(json.dumps(ambient, sort_keys=True) + "\n")
                log.flush()

            for trial_index in range(args.trials):
                for profile in profiles:
                    result = _run_trial(hmi, args.cluster, profile, trial_index, args)
                    print(json.dumps(result, sort_keys=True))
                    log.write(json.dumps(result, sort_keys=True) + "\n")
                    log.flush()
                    if args.pause_between > 0:
                        time.sleep(args.pause_between)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MazeException as exc:
        print(json.dumps({"event": "error", "error": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
