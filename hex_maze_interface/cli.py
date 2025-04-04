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
    cluster_ip_addresses = hmi.discover_cluster_ip_addresses()
    print(cluster_ip_addresses)

@cli.command()
@click.pass_obj
def get_cluster_address_map(hmi):
    cluster_address_map = hmi.get_cluster_address_map()
    print(cluster_address_map)

@cli.command()
@click.pass_obj
def reset(hmi):
    hmi.reset()

@cli.command()
@click.pass_obj
def power_off(hmi):
    hmi.power_off()

@cli.command()
@click.pass_obj
def power_on(hmi):
    hmi.power_on()

