"""Command line interface for the HexMazeInterface."""
import click
import os
from ipaddress import ip_address, IPv4Address, IPv6Address

from .hex_maze_interface import HexMazeInterface


interface = HexMazeInterface()

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

@click.command(context_settings=CONTEXT_SETTINGS)
@click.option('--ip', help='IP address to connect to')
def cli(ip):
    """Command line interface to the Voigts lab hex maze."""
    clear_screen()
    click.echo(f"Connecting to {ip}")
    interface.connect(ip)
    interface.send_led_on()

def clear_screen():
    """Clear command line for various operating systems."""
    if (os.name == 'posix'):
        os.system('clear')
    else:
        os.system('cls')
