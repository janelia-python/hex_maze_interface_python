"""Command line interface for the HexMazeInterface."""
import click
import os

from .hex_maze_interface import HexMazeInterface


@click.group()
@click.pass_context
def cli(ctx):
    ctx.obj = HexMazeInterface()

@cli.command()
@click.pass_obj
def discover(hmi):
    cluster_addresses = hmi.discover_cluster_addresses()
    print(cluster_addresses)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def check(hmi, cluster_address):
    if hmi.check_communication(cluster_address):
        print('communicating')
    else:
        print('not communicating!')

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def no_cmd(hmi, cluster_address):
    if hmi.no_cmd(cluster_address):
        print('no command received proper error response')
    else:
        print('no command did not receive proper error response!')

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def bad_cmd(hmi, cluster_address):
    if hmi.bad_cmd(cluster_address):
        print('bad command received proper error response')
    else:
        print('bad command did not receive proper error response!')

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def reset(hmi, cluster_address):
    if hmi.reset(cluster_address):
        print('resetting')
    else:
        print('not resetting')

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('duration-ms', nargs=1, type=int)
@click.pass_obj
def beep(hmi, cluster_address, duration_ms):
    hmi.beep(cluster_address, duration_ms)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def led_off(hmi, cluster_address):
    hmi.led_off(cluster_address)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def led_on(hmi, cluster_address):
    hmi.led_on(cluster_address)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def power_off(hmi, cluster_address):
    hmi.power_off(cluster_address)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def power_on(hmi, cluster_address):
    hmi.power_on(cluster_address)

