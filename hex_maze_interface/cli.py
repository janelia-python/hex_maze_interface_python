"""Command line interface for the HexMazeInterface."""

from __future__ import annotations

import json
from typing import Any

import click

from .hex_maze_interface import (
    ControllerParameters,
    HexMazeInterface,
    HomeParameters,
)


pass_hex_maze_interface = click.make_pass_decorator(HexMazeInterface)


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(value, indent=2, sort_keys=True))
    else:
        click.echo(value)


def _home_parameters(
    travel_limit: int,
    max_velocity: int,
    run_current: int,
    stall_threshold: int,
) -> HomeParameters:
    return HomeParameters(
        travel_limit=travel_limit,
        max_velocity=max_velocity,
        run_current=run_current,
        stall_threshold=stall_threshold,
    )


def _controller_parameters(
    start_velocity: int,
    stop_velocity: int,
    first_velocity: int,
    max_velocity: int,
    first_acceleration: int,
    max_acceleration: int,
    max_deceleration: int,
    first_deceleration: int,
) -> ControllerParameters:
    return ControllerParameters(
        start_velocity=start_velocity,
        stop_velocity=stop_velocity,
        first_velocity=first_velocity,
        max_velocity=max_velocity,
        first_acceleration=first_acceleration,
        max_acceleration=max_acceleration,
        max_deceleration=max_deceleration,
        first_deceleration=first_deceleration,
    )


@click.group()
@click.option("--debug/--no-debug", default=False, show_default=True)
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=1.0,
    show_default=True,
    help="Socket timeout in seconds. Use 0 to block indefinitely.",
)
@click.pass_context
def cli(ctx: click.Context, debug: bool, timeout_s: float) -> None:
    """Command line interface to the Voigts lab hex maze."""
    ctx.obj = HexMazeInterface(debug=debug, timeout_s=None if timeout_s <= 0 else timeout_s)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@pass_hex_maze_interface
def discover_clusters(hmi: HexMazeInterface, as_json: bool) -> None:
    _emit(hmi.discover_cluster_addresses(), as_json=as_json)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def communicating_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.communicating_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def communicating_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.communicating_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def reset_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.reset_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def reset_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.reset_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("duration-ms", type=int)
@pass_hex_maze_interface
def beep_cluster(hmi: HexMazeInterface, cluster_address: int, duration_ms: int) -> None:
    _emit(hmi.beep_cluster(cluster_address, duration_ms), as_json=False)


@cli.command()
@click.argument("duration-ms", type=int)
@pass_hex_maze_interface
def beep_all_clusters(hmi: HexMazeInterface, duration_ms: int) -> None:
    _emit(hmi.beep_all_clusters(duration_ms), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def led_off_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.led_off_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def led_off_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.led_off_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def led_on_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.led_on_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def led_on_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.led_on_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def power_off_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.power_off_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def power_off_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.power_off_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def power_on_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.power_on_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def power_on_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.power_on_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("prism-address", type=int)
@click.argument("travel-limit", type=int)
@click.argument("max-velocity", type=int)
@click.argument("run-current", type=int)
@click.argument("stall-threshold", type=int)
@pass_hex_maze_interface
def home_prism(
    hmi: HexMazeInterface,
    cluster_address: int,
    prism_address: int,
    travel_limit: int,
    max_velocity: int,
    run_current: int,
    stall_threshold: int,
) -> None:
    _emit(
        hmi.home_prism(
            cluster_address,
            prism_address,
            _home_parameters(travel_limit, max_velocity, run_current, stall_threshold),
        ),
        as_json=False,
    )


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("travel-limit", type=int)
@click.argument("max-velocity", type=int)
@click.argument("run-current", type=int)
@click.argument("stall-threshold", type=int)
@pass_hex_maze_interface
def home_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    travel_limit: int,
    max_velocity: int,
    run_current: int,
    stall_threshold: int,
) -> None:
    _emit(
        hmi.home_cluster(
            cluster_address,
            _home_parameters(travel_limit, max_velocity, run_current, stall_threshold),
        ),
        as_json=False,
    )


@cli.command()
@click.argument("travel-limit", type=int)
@click.argument("max-velocity", type=int)
@click.argument("run-current", type=int)
@click.argument("stall-threshold", type=int)
@pass_hex_maze_interface
def home_all_clusters(
    hmi: HexMazeInterface,
    travel_limit: int,
    max_velocity: int,
    run_current: int,
    stall_threshold: int,
) -> None:
    _emit(
        hmi.home_all_clusters(
            _home_parameters(travel_limit, max_velocity, run_current, stall_threshold)
        ),
        as_json=False,
    )


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def homed_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.homed_cluster(cluster_address), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@pass_hex_maze_interface
def read_home_outcomes_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    as_json: bool,
) -> None:
    outcomes = [outcome.name.lower() for outcome in hmi.read_home_outcomes_cluster(cluster_address)]
    _emit(outcomes, as_json=as_json)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("prism-address", type=int)
@click.argument("position-mm", type=int)
@pass_hex_maze_interface
def write_target_prism(
    hmi: HexMazeInterface,
    cluster_address: int,
    prism_address: int,
    position_mm: int,
) -> None:
    _emit(hmi.write_target_prism(cluster_address, prism_address, position_mm), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("positions-mm", nargs=HexMazeInterface.PRISM_COUNT, type=int)
@pass_hex_maze_interface
def write_targets_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    positions_mm: tuple[int, ...],
) -> None:
    _emit(hmi.write_targets_cluster(cluster_address, positions_mm), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("prism-address", type=int)
@pass_hex_maze_interface
def pause_prism(hmi: HexMazeInterface, cluster_address: int, prism_address: int) -> None:
    _emit(hmi.pause_prism(cluster_address, prism_address), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def pause_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.pause_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def pause_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.pause_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("prism-address", type=int)
@pass_hex_maze_interface
def resume_prism(hmi: HexMazeInterface, cluster_address: int, prism_address: int) -> None:
    _emit(hmi.resume_prism(cluster_address, prism_address), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def resume_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.resume_cluster(cluster_address), as_json=False)


@cli.command()
@pass_hex_maze_interface
def resume_all_clusters(hmi: HexMazeInterface) -> None:
    _emit(hmi.resume_all_clusters(), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def read_positions_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.read_positions_cluster(cluster_address), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("current-percent", type=int)
@pass_hex_maze_interface
def write_run_current_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    current_percent: int,
) -> None:
    _emit(hmi.write_run_current_cluster(cluster_address, current_percent), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def read_run_current_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(hmi.read_run_current_cluster(cluster_address), as_json=False)


@cli.command()
@click.argument("current-percent", type=int)
@pass_hex_maze_interface
def write_run_current_all_clusters(hmi: HexMazeInterface, current_percent: int) -> None:
    _emit(hmi.write_run_current_all_clusters(current_percent), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("start-velocity", type=int)
@click.argument("stop-velocity", type=int)
@click.argument("first-velocity", type=int)
@click.argument("max-velocity", type=int)
@click.argument("first-acceleration", type=int)
@click.argument("max-acceleration", type=int)
@click.argument("max-deceleration", type=int)
@click.argument("first-deceleration", type=int)
@pass_hex_maze_interface
def write_controller_parameters_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    start_velocity: int,
    stop_velocity: int,
    first_velocity: int,
    max_velocity: int,
    first_acceleration: int,
    max_acceleration: int,
    max_deceleration: int,
    first_deceleration: int,
) -> None:
    _emit(
        hmi.write_controller_parameters_cluster(
            cluster_address,
            _controller_parameters(
                start_velocity,
                stop_velocity,
                first_velocity,
                max_velocity,
                first_acceleration,
                max_acceleration,
                max_deceleration,
                first_deceleration,
            ),
        ),
        as_json=False,
    )


@cli.command()
@click.argument("start-velocity", type=int)
@click.argument("stop-velocity", type=int)
@click.argument("first-velocity", type=int)
@click.argument("max-velocity", type=int)
@click.argument("first-acceleration", type=int)
@click.argument("max-acceleration", type=int)
@click.argument("max-deceleration", type=int)
@click.argument("first-deceleration", type=int)
@pass_hex_maze_interface
def write_controller_parameters_all_clusters(
    hmi: HexMazeInterface,
    start_velocity: int,
    stop_velocity: int,
    first_velocity: int,
    max_velocity: int,
    first_acceleration: int,
    max_acceleration: int,
    max_deceleration: int,
    first_deceleration: int,
) -> None:
    _emit(
        hmi.write_controller_parameters_all_clusters(
            _controller_parameters(
                start_velocity,
                stop_velocity,
                first_velocity,
                max_velocity,
                first_acceleration,
                max_acceleration,
                max_deceleration,
                first_deceleration,
            )
        ),
        as_json=False,
    )


@cli.command()
@click.argument("cluster-address", type=int)
@pass_hex_maze_interface
def read_controller_parameters_cluster(hmi: HexMazeInterface, cluster_address: int) -> None:
    _emit(str(hmi.read_controller_parameters_cluster(cluster_address)), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("prism-address", type=int)
@click.argument("double-position-mm", nargs=2, type=int)
@pass_hex_maze_interface
def write_double_target_prism(
    hmi: HexMazeInterface,
    cluster_address: int,
    prism_address: int,
    double_position_mm: tuple[int, int],
) -> None:
    _emit(
        hmi.write_double_target_prism(cluster_address, prism_address, double_position_mm),
        as_json=False,
    )


@cli.command()
@click.argument("cluster-address", type=int)
@click.argument("double-positions-mm", nargs=HexMazeInterface.PRISM_COUNT * 2, type=int)
@pass_hex_maze_interface
def write_double_targets_cluster(
    hmi: HexMazeInterface,
    cluster_address: int,
    double_positions_mm: tuple[int, ...],
) -> None:
    pairs = tuple(
        double_positions_mm[index : index + 2]
        for index in range(0, len(double_positions_mm), 2)
    )
    _emit(hmi.write_double_targets_cluster(cluster_address, pairs), as_json=False)


@cli.command()
@click.argument("cluster-address", type=int)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@pass_hex_maze_interface
def verify_cluster(hmi: HexMazeInterface, cluster_address: int, as_json: bool) -> None:
    _emit(hmi.verify_cluster(cluster_address), as_json=as_json)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@pass_hex_maze_interface
def verify_all_clusters(hmi: HexMazeInterface, as_json: bool) -> None:
    _emit(hmi.verify_all_clusters(), as_json=as_json)
