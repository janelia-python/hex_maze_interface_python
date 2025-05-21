"""Command line interface for the HexMazeInterface."""
import click
import os

from .hex_maze_interface import HexMazeInterface, MazeException


@click.group()
@click.pass_context
def cli(ctx):
    ctx.obj = HexMazeInterface(debug=False)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def communicating_cluster(hmi, cluster_address):
    print(hmi.communicating_cluster(cluster_address))

@cli.command()
@click.pass_obj
def communicating_all_clusters(hmi):
    print(hmi.communicating_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def reset_cluster(hmi, cluster_address):
    print(hmi.reset_cluster(cluster_address))

@cli.command()
@click.pass_obj
def reset_all_clusters(hmi):
    print(hmi.reset_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('duration-ms', nargs=1, type=int)
@click.pass_obj
def beep_cluster(hmi, cluster_address, duration_ms):
    print(hmi.beep_cluster(cluster_address, duration_ms))

@cli.command()
@click.argument('duration-ms', nargs=1, type=int)
@click.pass_obj
def beep_all_clusters(hmi, duration_ms):
    print(hmi.beep_all_clusters(duration_ms))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def led_off_cluster(hmi, cluster_address):
    print(hmi.led_off_cluster(cluster_address))

@cli.command()
@click.pass_obj
def led_off_all_clusters(hmi):
    print(hmi.led_off_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def led_on_cluster(hmi, cluster_address):
    print(hmi.led_on_cluster(cluster_address))

@cli.command()
@click.pass_obj
def led_on_all_clusters(hmi):
    print(hmi.led_on_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def power_off_cluster(hmi, cluster_address):
    print(hmi.power_off_cluster(cluster_address))

@cli.command()
@click.pass_obj
def power_off_all_clusters(hmi):
    print(hmi.power_off_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def power_on_cluster(hmi, cluster_address):
    print(hmi.power_on_cluster(cluster_address))

@cli.command()
@click.pass_obj
def power_on_all_clusters(hmi):
    print(hmi.power_on_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('prism-address', nargs=1, type=int)
@click.argument('travel-limit', nargs=1, type=int)
@click.argument('speed', nargs=1, type=int)
@click.argument('stall-threshold', nargs=1, type=int)
@click.pass_obj
def home_prism(hmi, cluster_address, prism_address, travel_limit, speed, stall_threshold):
    print(hmi.home_prism(cluster_address, prism_address, travel_limit, speed, stall_threshold))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def home_cluster(hmi, cluster_address):
    print(hmi.home_cluster(cluster_address))

@cli.command()
@click.pass_obj
def home_all_clusters(hmi):
    print(hmi.home_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def homed_cluster(hmi, cluster_address):
    print(hmi.homed_cluster(cluster_address))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('prism-address', nargs=1, type=int)
@click.argument('position-mm', nargs=1, type=int)
@click.pass_obj
def write_target_prism(hmi, cluster_address, prism_address, position_mm):
    print(hmi.write_target_prism(cluster_address, prism_address, position_mm))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('positions-mm', nargs=HexMazeInterface.PRISM_COUNT, type=int)
@click.pass_obj
def write_targets_cluster(hmi, cluster_address, positions_mm):
    print(hmi.write_targets_cluster(cluster_address, positions_mm))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('prism-address', nargs=1, type=int)
@click.pass_obj
def pause_prism(hmi, cluster_address, prism_address):
    print(hmi.pause_prism(cluster_address, prism_address))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def pause_cluster(hmi, cluster_address):
    print(hmi.pause_cluster(cluster_address))

@cli.command()
@click.pass_obj
def pause_all_clusters(hmi):
    print(hmi.pause_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('prism-address', nargs=1, type=int)
@click.pass_obj
def resume_prism(hmi, cluster_address, prism_address):
    print(hmi.resume_prism(cluster_address, prism_address))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def resume_cluster(hmi, cluster_address):
    print(hmi.resume_cluster(cluster_address))

@cli.command()
@click.pass_obj
def resume_all_clusters(hmi):
    print(hmi.resume_all_clusters())

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def read_actual_positions_cluster(hmi, cluster_address):
    actual_positions = hmi.read_actual_positions_cluster(cluster_address)
    print(actual_positions)

