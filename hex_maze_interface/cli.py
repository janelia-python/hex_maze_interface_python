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
def say_hello(hmi):
    hmi.say_hello()

@cli.command()
@click.pass_obj
def discover_cluster_ip_addresses(hmi):
    cluster_ip_addresses = hmi.discover_cluster_ip_addresses()
    print(cluster_ip_addresses)

@cli.command()
@click.pass_obj
def get_cluster_address_map(hmi):
    cluster_address_map = hmi.get_cluster_address_map()
    print(cluster_address_map)

@cli.command()
@click.pass_obj
def find_serial_ports(hmi):
    print(hmi.find_serial_ports())

@cli.command()
@click.pass_obj
def connect_serial(hmi):
    print(hmi.connect_serial())

@cli.command()
@click.pass_obj
def led_on_str(hmi):
    hmi.led_on_str()

@cli.command()
@click.pass_obj
def led_off_str(hmi):
    hmi.led_off_str()

# interface = HexMazeInterface()

# CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

# @click.command(context_settings=CONTEXT_SETTINGS)
# @click.option('--ip', help='IP address to connect to')
# def cli(ip):
#     """Command line interface to the Voigts lab hex maze."""
#     clear_screen()
#     click.echo(f"Connecting to {ip}")
#     interface.connect(ip)
#     interface.send_led_on()

# def clear_screen():
#     """Clear command line for various operating systems."""
#     if (os.name == 'posix'):
#         os.system('clear')
#     else:
#         os.system('cls')
