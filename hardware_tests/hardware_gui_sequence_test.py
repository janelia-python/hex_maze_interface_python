#!/usr/bin/env python3
"""Exercise the researcher GUI initialization and motion sequence on live hardware."""

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
    parser.add_argument("--clusters", type=int, nargs="+", required=True)
    parser.add_argument(
        "--use-all-clusters-api",
        action="store_true",
        help=(
            "Use power/controller/home all-cluster API methods. Intended for a fully attached rig."
        ),
    )
    parser.add_argument(
        "--home-travel-limit",
        type=int,
        default=100,
        help="Researcher-supervised incremental home travel.",
    )
    parser.add_argument("--home-max-velocity", type=int, default=10)
    parser.add_argument("--home-run-current", type=int, default=43)
    parser.add_argument("--home-stall-threshold", type=int, default=0)
    parser.add_argument("--position-timeout", type=float, default=20.0)
    parser.add_argument("--home-timeout", type=float, default=25.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--position-tolerance", type=int, default=5)
    parser.add_argument("--start-velocity", type=int, default=10)
    parser.add_argument("--stop-velocity", type=int, default=10)
    parser.add_argument("--first-velocity", type=int, default=40)
    parser.add_argument("--max-velocity", type=int, default=40)
    parser.add_argument("--first-acceleration", type=int, default=120)
    parser.add_argument("--max-acceleration", type=int, default=80)
    parser.add_argument("--max-deceleration", type=int, default=80)
    parser.add_argument("--first-deceleration", type=int, default=120)
    parser.add_argument(
        "--exercise-double-targets",
        action="store_true",
        help="Also send a representative write_double_targets_cluster sequence.",
    )
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
            time.sleep(poll_interval_s)
            settled = {
                "homed": tuple(bool(value) for value in hmi.homed_cluster(cluster_address)),
                "outcomes": tuple(hmi.read_home_outcomes_cluster(cluster_address)),
                "positions_mm": tuple(hmi.read_positions_cluster(cluster_address)),
            }
            return {
                "homed": list(settled["homed"]),
                "outcomes": [outcome.name for outcome in settled["outcomes"]],
                "positions_mm": list(settled["positions_mm"]),
            }
        if any(outcome == HomeOutcome.FAILED for outcome in last["outcomes"]):
            raise MazeException(
                f"cluster {cluster_address} reported failed home outcome: "
                f"{[outcome.name for outcome in last['outcomes']]}"
            )
        time.sleep(poll_interval_s)
    raise MazeException(f"cluster {cluster_address} did not finish homing; last state was {last}")


def _verify_cluster_alive(hmi: HexMazeInterface, cluster_address: int) -> dict[str, object]:
    report = hmi.verify_cluster(cluster_address)
    if not report["checks"].get("communicating", False):
        raise MazeException(f"cluster {cluster_address} failed communication check: {report}")
    return report


def _power_cycle_clusters(hmi: HexMazeInterface, clusters: tuple[int, ...]) -> dict[str, object]:
    power_off = {cluster: hmi.power_off_cluster(cluster) for cluster in clusters}
    if not all(power_off.values()):
        raise MazeException(f"power_off_cluster failed: {power_off}")
    power_on = {cluster: hmi.power_on_cluster(cluster) for cluster in clusters}
    if not all(power_on.values()):
        raise MazeException(f"power_on_cluster failed: {power_on}")
    return {"power_off": power_off, "power_on": power_on}


def _power_cycle_all_clusters_api(
    hmi: HexMazeInterface, clusters: tuple[int, ...]
) -> dict[str, object]:
    power_off = hmi.power_off_all_clusters()
    power_on = hmi.power_on_all_clusters()
    expected = set(clusters)
    indexed_power_off = {
        cluster: power_off[index]
        for index, cluster in enumerate(hmi.CLUSTER_ADDRESSES)
        if cluster in expected
    }
    indexed_power_on = {
        cluster: power_on[index]
        for index, cluster in enumerate(hmi.CLUSTER_ADDRESSES)
        if cluster in expected
    }
    if not all(indexed_power_off.values()):
        raise MazeException(
            f"power_off_all_clusters failed for selected clusters: {indexed_power_off}"
        )
    if not all(indexed_power_on.values()):
        raise MazeException(
            f"power_on_all_clusters failed for selected clusters: {indexed_power_on}"
        )
    return {"power_off_all_clusters": indexed_power_off, "power_on_all_clusters": indexed_power_on}


def _configure_controller_parameters(args: argparse.Namespace) -> ControllerParameters:
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


def _write_controller_parameters(
    hmi: HexMazeInterface,
    clusters: tuple[int, ...],
    controller_parameters: ControllerParameters,
    use_all_clusters_api: bool,
) -> dict[str, object]:
    if use_all_clusters_api:
        results = hmi.write_controller_parameters_all_clusters(controller_parameters)
        selected = {
            cluster: results[index]
            for index, cluster in enumerate(hmi.CLUSTER_ADDRESSES)
            if cluster in set(clusters)
        }
    else:
        selected = {
            cluster: hmi.write_controller_parameters_cluster(cluster, controller_parameters)
            for cluster in clusters
        }
    if not all(selected.values()):
        raise MazeException(f"controller parameter write failed: {selected}")
    return selected


def _verify_controller_parameters(
    hmi: HexMazeInterface,
    clusters: tuple[int, ...],
    controller_parameters: ControllerParameters,
) -> dict[int, dict[str, object]]:
    expected = controller_parameters.to_tuple()
    reports: dict[int, dict[str, object]] = {}
    for cluster in clusters:
        actual = hmi.read_controller_parameters_cluster(cluster).to_tuple()
        if actual != expected:
            raise MazeException(
                "cluster "
                f"{cluster} controller parameters mismatch: "
                f"expected {expected}, got {actual}"
            )
        reports[cluster] = {"expected": list(expected), "actual": list(actual)}
    return reports


def _home_clusters(
    hmi: HexMazeInterface,
    clusters: tuple[int, ...],
    home_parameters: HomeParameters,
    use_all_clusters_api: bool,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[int, dict[str, object]]:
    if use_all_clusters_api:
        start_results = hmi.home_all_clusters(home_parameters)
        selected = {
            cluster: start_results[index]
            for index, cluster in enumerate(hmi.CLUSTER_ADDRESSES)
            if cluster in set(clusters)
        }
    else:
        selected = {cluster: hmi.home_cluster(cluster, home_parameters) for cluster in clusters}
    if not all(selected.values()):
        raise MazeException(f"home start failed: {selected}")
    reports = {
        cluster: _wait_for_home(hmi, cluster, timeout_s, poll_interval_s) for cluster in clusters
    }
    for cluster, report in reports.items():
        if not all(report["homed"]):
            raise MazeException(f"cluster {cluster} did not fully home: {report}")
    return reports


def _cluster_targets_for_index(cluster_index: int) -> tuple[int, ...]:
    base = 90 + cluster_index * 5
    return tuple(base + 10 * prism_index for prism_index in range(HexMazeInterface.PRISM_COUNT))


def _double_targets_for_targets(targets_mm: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    return tuple((max(0, target - 45), target) for target in targets_mm)


def _run_cluster_motion(
    hmi: HexMazeInterface,
    cluster_address: int,
    cluster_index: int,
    args: argparse.Namespace,
) -> dict[str, object]:
    targets_mm = _cluster_targets_for_index(cluster_index)
    if not hmi.write_targets_cluster(cluster_address, targets_mm):
        raise MazeException(f"cluster {cluster_address} write_targets_cluster failed")
    final_positions = _wait_for_positions(
        hmi,
        cluster_address,
        targets_mm,
        args.position_timeout,
        args.poll_interval,
        args.position_tolerance,
    )
    report: dict[str, object] = {
        "targets_mm": list(targets_mm),
        "final_positions_mm": list(final_positions),
    }

    if args.exercise_double_targets:
        double_targets_mm = _double_targets_for_targets(targets_mm)
        if not hmi.write_double_targets_cluster(cluster_address, double_targets_mm):
            raise MazeException(f"cluster {cluster_address} write_double_targets_cluster failed")
        double_final_positions = _wait_for_positions(
            hmi,
            cluster_address,
            tuple(target for _, target in double_targets_mm),
            args.position_timeout,
            args.poll_interval,
            args.position_tolerance,
        )
        report["double_targets_mm"] = [list(pair) for pair in double_targets_mm]
        report["double_final_positions_mm"] = list(double_final_positions)

    return report


def main() -> int:
    args = _parse_args()
    clusters = tuple(args.clusters)
    home_parameters = HomeParameters(
        travel_limit=args.home_travel_limit,
        max_velocity=args.home_max_velocity,
        run_current=args.home_run_current,
        stall_threshold=args.home_stall_threshold,
    )
    controller_parameters = _configure_controller_parameters(args)

    with HexMazeInterface(debug=args.debug) as hmi:
        if args.use_all_clusters_api and set(clusters) != set(hmi.CLUSTER_ADDRESSES):
            raise MazeException("--use-all-clusters-api requires selecting all cluster addresses")

        power_cycle = (
            _power_cycle_all_clusters_api(hmi, clusters)
            if args.use_all_clusters_api
            else _power_cycle_clusters(hmi, clusters)
        )
        verify_after_power = {cluster: _verify_cluster_alive(hmi, cluster) for cluster in clusters}
        controller_write = _write_controller_parameters(
            hmi,
            clusters,
            controller_parameters,
            args.use_all_clusters_api,
        )
        verify_after_controller = _verify_controller_parameters(
            hmi,
            clusters,
            controller_parameters,
        )
        home_reports = _home_clusters(
            hmi,
            clusters,
            home_parameters,
            args.use_all_clusters_api,
            args.home_timeout,
            args.poll_interval,
        )
        motion_reports = {
            cluster: _run_cluster_motion(hmi, cluster, index, args)
            for index, cluster in enumerate(clusters)
        }

    print(
        json.dumps(
            {
                "clusters": list(clusters),
                "use_all_clusters_api": args.use_all_clusters_api,
                "controller_parameters": controller_parameters.to_tuple(),
                "home_parameters": home_parameters.to_tuple(),
                "power_cycle": power_cycle,
                "verify_after_power": verify_after_power,
                "controller_write": controller_write,
                "verify_after_controller": verify_after_controller,
                "home": home_reports,
                "motion": motion_reports,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
