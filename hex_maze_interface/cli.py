"""Command line interface for the HexMazeInterface."""
import click
import os

from .hex_maze_interface import HexMazeInterface, MazeException, HomeParameters, ControllerParameters

@click.group()
@click.pass_context
def cli(ctx):
    """Command line interface to the Voigts lab hex maze."""
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
@click.argument('max-velocity', nargs=1, type=int)
@click.argument('run-current', nargs=1, type=int)
@click.argument('stall-threshold', nargs=1, type=int)
@click.pass_obj
def home_prism(hmi,
               cluster_address,
               prism_address,
               travel_limit,
               max_velocity,
               run_current,
               stall_threshold):
    home_parameters = HomeParameters(travel_limit,
                                     max_velocity,
                                     run_current,
                                     stall_threshold)
    print(hmi.home_prism(cluster_address, prism_address, home_parameters))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('travel-limit', nargs=1, type=int)
@click.argument('max-velocity', nargs=1, type=int)
@click.argument('run-current', nargs=1, type=int)
@click.argument('stall-threshold', nargs=1, type=int)
@click.pass_obj
def home_cluster(hmi,
                 cluster_address,
                 travel_limit,
                 max_velocity,
                 run_current,
                 stall_threshold):
    home_parameters = HomeParameters(travel_limit,
                                     max_velocity,
                                     run_current,
                                     stall_threshold)
    print(hmi.home_cluster(cluster_address, home_parameters))

@cli.command()
@click.pass_obj
@click.argument('travel-limit', nargs=1, type=int)
@click.argument('max-velocity', nargs=1, type=int)
@click.argument('run-current', nargs=1, type=int)
@click.argument('stall-threshold', nargs=1, type=int)
def home_all_clusters(hmi,
                      travel_limit,
                      max_velocity,
                      run_current,
                      stall_threshold):
    home_parameters = HomeParameters(travel_limit,
                                     max_velocity,
                                     run_current,
                                     stall_threshold)
    print(hmi.home_all_clusters(home_parameters))

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
def read_positions_cluster(hmi, cluster_address):
    positions = hmi.read_positions_cluster(cluster_address)
    print(positions)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('current-percent', nargs=1, type=int)
@click.pass_obj
def write_run_current_cluster(hmi, cluster_address, current_percent):
    print(hmi.write_run_current_cluster(cluster_address, current_percent))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def read_run_current_cluster(hmi, cluster_address):
    run_current = hmi.read_run_current_cluster(cluster_address)
    print(run_current)

@cli.command()
@click.argument('current-percent', nargs=1, type=int)
@click.pass_obj
def write_run_current_all_clusters(hmi, current_percent):
    print(hmi.write_run_current_all_clusters(current_percent))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('start-velocity', nargs=1, type=int)
@click.argument('stop-velocity', nargs=1, type=int)
@click.argument('first-velocity', nargs=1, type=int)
@click.argument('max-velocity', nargs=1, type=int)
@click.argument('first-acceleration', nargs=1, type=int)
@click.argument('max-acceleration', nargs=1, type=int)
@click.argument('max-deceleration', nargs=1, type=int)
@click.argument('first-deceleration', nargs=1, type=int)
@click.pass_obj
def write_controller_parameters_cluster(hmi,
                                        cluster_address,
                                        start_velocity,
                                        stop_velocity,
                                        first_velocity,
                                        max_velocity,
                                        first_acceleration,
                                        max_acceleration,
                                        max_deceleration,
                                        first_deceleration):
    controller_parameters = ControllerParameters(start_velocity,
                                                 stop_velocity,
                                                 first_velocity,
                                                 max_velocity,
                                                 first_acceleration,
                                                 max_acceleration,
                                                 max_deceleration,
                                                 first_deceleration)
    print(hmi.write_controller_parameters_cluster(cluster_address, controller_parameters))

@cli.command()
@click.argument('start-velocity', nargs=1, type=int)
@click.argument('stop-velocity', nargs=1, type=int)
@click.argument('first-velocity', nargs=1, type=int)
@click.argument('max-velocity', nargs=1, type=int)
@click.argument('first-acceleration', nargs=1, type=int)
@click.argument('max-acceleration', nargs=1, type=int)
@click.argument('max-deceleration', nargs=1, type=int)
@click.argument('first-deceleration', nargs=1, type=int)
@click.pass_obj
def write_controller_parameters_all_clusters(hmi,
                                             start_velocity,
                                             stop_velocity,
                                             first_velocity,
                                             max_velocity,
                                             first_acceleration,
                                             max_acceleration,
                                             max_deceleration,
                                             first_deceleration):
    controller_parameters = ControllerParameters(start_velocity,
                                                 stop_velocity,
                                                 first_velocity,
                                                 max_velocity,
                                                 first_acceleration,
                                                 max_acceleration,
                                                 max_deceleration,
                                                 first_deceleration)
    print(hmi.write_controller_parameters_all_clusters(controller_parameters))

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.pass_obj
def read_controller_parameters_cluster(hmi, cluster_address):
    controller_parameters = hmi.read_controller_parameters_cluster(cluster_address)
    print(controller_parameters)

@cli.command()
@click.argument('cluster-address', nargs=1, type=int)
@click.argument('prism-address', nargs=1, type=int)
@click.argument('double-position-mm', nargs=2, type=int)
@click.pass_obj
def write_double_target_prism(hmi, cluster_address, prism_address, double_position_mm):
    print(hmi.write_double_target_prism(cluster_address, prism_address, double_position_mm))

