- [About](#orgad89128)
- [Protocol](#org1893526)
- [Background](#org8de352a)
- [Example Usage](#org4578627)
- [Installation](#org842bf6b)
- [Development](#org671fd47)

    <!-- This file is generated automatically from metadata -->
    <!-- File edits may be overwritten! -->


<a id="orgad89128"></a>

# About

```markdown
- Python Package Name: hex_maze_interface
- Description: Python interface to the Voigts lab hex maze.
- Version: 4.0.0
- Python Version: 3.11
- Release Date: 2025-06-11
- Creation Date: 2024-01-14
- License: BSD-3-Clause
- URL: https://github.com/janelia-python/hex_maze_interface_python
- Author: Peter Polidoro
- Email: peter@polidoro.io
- Copyright: 2025 Howard Hughes Medical Institute
- References:
  - https://github.com/janelia-experimental-technology/hex-maze
  - https://github.com/janelia-kicad/prism-pcb
  - https://github.com/janelia-kicad/cluster-pcb
  - https://github.com/janelia-arduino/ClusterController
  - https://github.com/janelia-arduino/TMC51X0
- Dependencies:
  - click
  - python3-nmap
```


<a id="org1893526"></a>

# Protocol

-   protocol-version = 0x04
-   prism-count = 7
-   command = protocol-version command-length command-number command-parameters
-   response = protocol-version response-length command-number response-parameters
-   duration units = ms
-   position units = mm
-   velocity units = mm/s
-   current units = percent
-   stall-threshold -> higher value = lower sensitivity, 0 indifferent value, 1..63 less sensitivity, -1..-64 higher sensitivity
-   home-parameters = travel-limit, max-velocity, run-current, stall-threshold
-   controller-parameters = start-velocity, stop-velocity, first-velocity, max-velocity, first-acceleration, max-acceleration, max-deceleration, first-deceleration
-   double-position = position-0, position-1

| command-name                        | command-format       | command-length | command-number | command-parameters             | response-format | response-length | response-parameters    |
|----------------------------------- |-------------------- |-------------- |-------------- |------------------------------ |--------------- |--------------- |---------------------- |
| invalid-command                     |                      |                |                |                                | '<BBB'          | 3               | 0xEE                   |
| read-cluster-address                | '<BBB'               | 3              | 0x01           |                                | '<BBBB'         | 4               | 0x00..0xFF             |
| communicating-cluster               | '<BBB'               | 3              | 0x02           |                                | '<BBBL'         | 7               | 0x12345678             |
| reset-cluster                       | '<BBB'               | 3              | 0x03           |                                | '<BBB'          | 3               |                        |
| beep-cluster                        | '<BBBH'              | 5              | 0x04           | duration                       | '<BBB'          | 3               |                        |
| led-off-cluster                     | '<BBB'               | 3              | 0x05           |                                | '<BBB'          | 3               |                        |
| led-on-cluster                      | '<BBB'               | 3              | 0x06           |                                | '<BBB'          | 3               |                        |
| power-off-cluster                   | '<BBB'               | 3              | 0x07           |                                | '<BBB'          | 3               |                        |
| power-on-cluster                    | '<BBB'               | 3              | 0x08           |                                | '<BBB'          | 3               |                        |
| home-prism                          | '<BBBBHBBb'          | 9              | 0x09           | prism-address, home-parameters | '<BBBB'         | 4               | prism-address          |
| home-cluster                        | '<BBBHBBb'           | 8              | 0x0A           | home-parameters                | '<BBB'          | 3               |                        |
| homed-cluster                       | '<BBB'               | 3              | 0x0B           |                                | '<BBBBBBBBBB'   | 10              | 0..1[prism-count]      |
| write-target-prism                  | '<BBBBH'             | 6              | 0x0C           | prism-address, position        | '<BBBB'         | 4               | prism-address          |
| write-targets-cluster               | '<BBBHHHHHHH'        | 17             | 0x0D           | position[prism-count]          | '<BBB'          | 3               |                        |
| pause-prism                         | '<BBBB'              | 4              | 0x0E           | prism-address                  | '<BBBB'         | 4               | prism-address          |
| pause-cluster                       | '<BBB'               | 3              | 0x0F           |                                | '<BBB'          | 3               |                        |
| resume-prism                        | '<BBBB'              | 4              | 0x10           | prism-address                  | '<BBBB'         | 4               | prism-address          |
| resume-cluster                      | '<BBB'               | 3              | 0x11           |                                | '<BBB'          | 3               |                        |
| read-positions-cluster              | '<BBB'               | 3              | 0x12           |                                | '<BBBhhhhhhh'   | 17              | -1..32767[prism-count] |
| write-run-current-cluster           | '<BBBB'              | 4              | 0x13           | run-current                    | '<BBB'          | 3               |                        |
| read-run-current-cluster            | '<BBB'               | 3              | 0x14           |                                | '<BBBB'         | 4               | run-current            |
| write-controller-parameters-cluster | '<BBBBBBBBBBB'       | 11             | 0x15           | controller-parameters          | '<BBB'          | 3               |                        |
| read-controller-parameters-cluster  | '<BBB'               | 3              | 0x16           |                                | '<BBBBBBBBBBB'  | 11              | controller-parameters  |
| write-double-target-prism           | '<BBBBHH'            | 8              | 0x17           | prism-address, double-position | '<BBBB'         | 4               | prism-address          |
| write-double-targets-cluster        | '<BBBHHHHHHHHHHHHHH' | 31             | 0x18           | double-position[prism-count]   | '<BBB'          | 3               |                        |


<a id="org8de352a"></a>

# Background

<img src="./documentation/img/ramp.png" width="1920">


<a id="org4578627"></a>

# Example Usage


## Python

```python
from hex_maze_interface import HexMazeInterface, MazeException, HomeParameters, ControllerParameters
hmi = HexMazeInterface()
cluster_address = 10
hmi.communicating_cluster(cluster_address)
hmi.reset_cluster(cluster_address)
duration_ms = 100
hmi.beep_cluster(cluster_address, duration_ms)
hmi.power_on_cluster(cluster_address)
prism_address = 2
home_parameters = HomeParameters()
home_parameters.travel_limit = 100
home_parameters.max_velocity = 20
home_parameters.run_current = 50
home_parameters.stall_threshold = 10
# a single prism may be homed
hmi.home_prism(cluster_address, prism_address, home_parameters)
# or all prisms in a cluster may be homed at the same time
hmi.home_cluster(cluster_address, home_parameters)
hmi.homed_cluster(cluster_address)
print(hmi.read_positions_cluster(cluster_address))
# a single prism may be commanded to move immediately
hmi.write_target_prism(cluster_address, prism_address, 100)
print(hmi.read_positions_cluster(cluster_address))
hmi.pause_cluster(cluster_address)
# or all prisms in a cluster may be commanded to move
hmi.write_targets_cluster(cluster_address, (10, 20, 30, 40, 50, 60, 70))
# but the prisms only move after resuming while pausing
hmi.resume_cluster(cluster_address)
print(hmi.read_positions_cluster(cluster_address))
print(hmi.read_run_current_cluster(cluster_address))
hmi.write_run_current_cluster(cluster_address, 80)
print(hmi.read_run_current_cluster(cluster_address))
print(hmi.read_controller_parameters_cluster(cluster_address))
controller_parameters = ControllerParameters()
controller_parameters.start_velocity = 1
controller_parameters.stop_velocity = 5
controller_parameters.first_velocity = 10
controller_parameters.max_velocity = 20
controller_parameters.first_acceleration = 40
controller_parameters.max_acceleration = 20
controller_parameters.max_deceleration = 30
controller_parameters.first_deceleration = 50
hmi.write_controller_parameters_cluster(cluster_address, controller_parameters)
print(hmi.read_controller_parameters_cluster(cluster_address))
hmi.write_target_prism(cluster_address, prism_address, 100)
hmi.write_double_target_prism(cluster_address, prism_address, (50, 150))
hmi.write_double_targets_cluster(cluster_address, ((10,20),(30,40),(50,60),(70,80),(90,100),(110,120),(130,140)))
hmi.power_off_cluster(cluster_address)
```


## Command Line


### Help

```sh
maze --help
# Usage: maze [OPTIONS] COMMAND [ARGS]...

#   Command line interface to the Voigts lab hex maze.

Options:
  --help  Show this message and exit.

Commands:
  beep-all-clusters
  beep-cluster
  communicating-all-clusters
  communicating-cluster
  home-all-clusters
  home-cluster
  home-prism
  homed-cluster
  led-off-all-clusters
  led-off-cluster
  led-on-all-clusters
  led-on-cluster
  pause-all-clusters
  pause-cluster
  pause-prism
  power-off-all-clusters
  power-off-cluster
  power-on-all-clusters
  power-on-cluster
  read-controller-parameters-cluster
  read-positions-cluster
  read-run-current-cluster
  reset-all-clusters
  reset-cluster
  resume-all-clusters
  resume-cluster
  resume-prism
  write-controller-parameters-all-clusters
  write-controller-parameters-cluster
  write-double-target-prism
  write-run-current-all-clusters
  write-run-current-cluster
  write-target-prism
  write-targets-cluster
```


### Example

```sh
CLUSTER_ADDRESS=10
maze communicating-cluster $CLUSTER_ADDRESS
maze reset-cluster $CLUSTER_ADDRESS
DURATION_MS=100
maze beep-cluster $CLUSTER_ADDRESS $DURATION_MS
maze power-on-cluster $CLUSTER_ADDRESS
PRISM_ADDRESS=2
TRAVEL_LIMIT=100
MAX_VELOCITY=20
RUN_CURRENT=50
STALL_THRESHOLD=10
# a single prism may be homed
maze home-prism $CLUSTER_ADDRESS $PRISM_ADDRESS $TRAVEL_LIMIT $MAX_VELOCITY $RUN_CURRENT $STALL_THRESHOLD
# or all prisms in a cluster may be homed at the same time
maze home-cluster $CLUSTER_ADDRESS $TRAVEL_LIMIT $MAX_VELOCITY $RUN_CURRENT $STALL_THRESHOLD
maze homed-cluster $CLUSTER_ADDRESS
maze read-positions-cluster $CLUSTER_ADDRESS
# a single prism may be commanded to move immediately
maze write-target-prism $CLUSTER_ADDRESS $PRISM_ADDRESS 100
maze read-positions-cluster $CLUSTER_ADDRESS
maze pause-cluster $CLUSTER_ADDRESS
# or all prisms in a cluster may be commanded to move
maze write-targets-cluster $CLUSTER_ADDRESS 10 20 30 40 50 60 70
# but the prisms only move after resuming while pausing
maze resume-cluster $CLUSTER_ADDRESS
maze read-positions-cluster $CLUSTER_ADDRESS
maze read-run-current-cluster $CLUSTER_ADDRESS
maze write-run-current-cluster $CLUSTER_ADDRESS 80
maze read-run-current-cluster $CLUSTER_ADDRESS
START_VELOCITY=1
STOP_VELOCITY=5
FIRST_VELOCITY=10
MAX_VELOCITY=20
FIRST_ACCELERATION=40
MAX_ACCELERATION=20
MAX_DECELERATION=30
FIRST_DECELERATION=50
maze write-controller-parameters-cluster $CLUSTER_ADDRESS \
$START_VELOCITY $STOP_VELOCITY $FIRST_VELOCITY $MAX_VELOCITY $FIRST_ACCELERATION \
$MAX_ACCELERATION $MAX_DECELERATION $FIRST_DECELERATION
maze write-target-prism $CLUSTER_ADDRESS $PRISM_ADDRESS 100
maze write-double-target-prism $CLUSTER_ADDRESS $PRISM_ADDRESS 50 150
maze power-off-cluster $CLUSTER_ADDRESS
```


<a id="org842bf6b"></a>

# Installation

<https://github.com/janelia-python/python_setup>


## GNU/Linux


### Ethernet

C-x C-f /sudo::/etc/network/interfaces

```sh
auto eth1

iface eth1 inet static

    address 192.168.10.2

    netmask 255.255.255.0

    gateway 192.168.10.1

    dns-nameserver 8.8.8.8 8.8.4.4
```

```sh
nmap -sn 192.168.10.0/24
nmap -p 7777 192.168.10.3
nmap -sV -p 80,7777 192.168.10.0/24
```

```sh
sudo -E guix shell nmap
sudo -E guix shell wireshark -- wireshark
```

```sh
make guix-container
```


### Serial

1.  Drivers

    GNU/Linux computers usually have all of the necessary drivers already installed, but users need the appropriate permissions to open the device and communicate with it.
    
    Udev is the GNU/Linux subsystem that detects when things are plugged into your computer.
    
    Udev may be used to detect when a device is plugged into the computer and automatically give permission to open that device.
    
    If you plug a sensor into your computer and attempt to open it and get an error such as: "FATAL: cannot open /dev/ttyACM0: Permission denied", then you need to install udev rules to give permission to open that device.
    
    Udev rules may be downloaded as a file and placed in the appropriate directory using these instructions:
    
    [99-platformio-udev.rules](https://docs.platformio.org/en/stable/core/installation/udev-rules.html)

2.  Download rules into the correct directory

    ```sh
    curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/master/scripts/99-platformio-udev.rules | sudo tee /etc/udev/rules.d/99-platformio-udev.rules
    ```

3.  Restart udev management tool

    ```sh
    sudo service udev restart
    ```

4.  Ubuntu/Debian users may need to add own “username” to the “dialout” group

    ```sh
    sudo usermod -a -G dialout $USER
    sudo usermod -a -G plugdev $USER
    ```

5.  After setting up rules and groups

    You will need to log out and log back in again (or reboot) for the user group changes to take effect.
    
    After this file is installed, physically unplug and reconnect your board.


## Python Code

The Python code in this library may be installed in any number of ways, chose one.

1.  pip

    ```sh
    python3 -m venv ~/venvs/hex_maze_interface
    source ~/venvs/hex_maze_interface/bin/activate
    pip install hex_maze_interface
    ```

2.  guix

    Setup guix-janelia channel:
    
    <https://github.com/guix-janelia/guix-janelia>
    
    ```sh
    guix install python-hex-maze-interface
    ```


## Windows


### Python Code

The Python code in this library may be installed in any number of ways, chose one.

1.  pip

    ```sh
    python3 -m venv C:\venvs\hex_maze_interface
    C:\venvs\hex_maze_interface\Scripts\activate
    pip install hex_maze_interface
    ```


<a id="org671fd47"></a>

# Development


## Clone Repository

```sh
git clone git@github.com:janelia-python/hex_maze_interface_python.git
cd hex_maze_interface_python
```


## Guix


### Install Guix

[Install Guix](https://guix.gnu.org/manual/en/html_node/Binary-Installation.html)


### Edit metadata.org

```sh
make -f .metadata/Makefile metadata-edits
```


### Tangle metadata.org

```sh
make -f .metadata/Makefile metadata
```


### Develop Python package

```sh
make -f .metadata/Makefile guix-dev-container
exit
```


### Test Python package using ipython shell

```sh
make -f .metadata/Makefile guix-dev-container-ipython
import hex_maze_interface
exit
```


### Test Python package installation

```sh
make -f .metadata/Makefile guix-container
exit
```


### Upload Python package to pypi

```sh
make -f .metadata/Makefile upload
```


### Test direct device interaction using serial terminal

```sh
make -f .metadata/Makefile guix-dev-container-port-serial # PORT=/dev/ttyACM0
# make -f .metadata/Makefile PORT=/dev/ttyACM1 guix-dev-container-port-serial
? # help
[C-a][C-x] # to exit
```


## Docker


### Install Docker Engine

<https://docs.docker.com/engine/>


### Develop Python package

```sh
make -f .metadata/Makefile docker-dev-container
exit
```


### Test Python package using ipython shell

```sh
make -f .metadata/Makefile docker-dev-container-ipython
import hex_maze_interface
exit
```


### Test Python package installation

```sh
make -f .metadata/Makefile docker-container
exit
```
