- [About](#org6e99c0c)
- [Example Usage](#orgb5c1bb9)
- [Background](#orgdcd0707)
- [Installation](#orgd5d651d)
- [Development](#orgc2b3a2e)

    <!-- This file is generated automatically from metadata -->
    <!-- File edits may be overwritten! -->


<a id="org6e99c0c"></a>

# About

```markdown
- Python Package Name: hex_maze_interface
- Description: Python interface to the Voigts lab hex maze.
- Version: 4.0.0
- Python Version: 3.11
- Release Date: 2025-06-03
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


<a id="orgb5c1bb9"></a>

# Example Usage


## Python

```python
from hex_maze_interface import HexMazeInterface, MazeException
hmi = HexMazeInterface()
cluster_address = 10
hmi.communicating_cluster(cluster_address)
hmi.reset_cluster(cluster_address)
duration_ms = 100
hmi.beep_cluster(cluster_address, duration_ms)
hmi.power_on_cluster(cluster_address)
prism_address = 2
travel_limit_mm = 100
speed_mm_per_s = 20
current_percent = 50
stall_threshold = 10
# a single prism may be homed
hmi.home_prism(cluster_address, prism_address, travel_limit_mm, speed_mm_per_s, current_percent, stall_threshold)
# or all prisms in a cluster may be homed at the same time
hmi.home_cluster(cluster_address, travel_limit_mm, speed_mm_per_s, current_percent, stall_threshold)
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
hmi.write_speed_cluster(cluster_address, 40)
hmi.write_current_cluster(cluster_address, 50)
hmi.write_target_prism(cluster_address, prism_address, 100)
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
  read-positions-cluster
  reset-all-clusters
  reset-cluster
  resume-all-clusters
  resume-cluster
  resume-prism
  write-current-all-clusters
  write-current-cluster
  write-speed-all-clusters
  write-speed-cluster
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
TRAVEL_LIMIT_MM=100
SPEED_MM_PER_S=20
CURRENT_PERCENT=50
STALL_THRESHOLD=10
# a single prism may be homed
maze home-prism $CLUSTER_ADDRESS $PRISM_ADDRESS $TRAVEL_LIMIT_MM $SPEED_MM_PER_S $CURRENT_PERCENT $STALL_THRESHOLD
# or all prisms in a cluster may be homed at the same time
maze home-cluster $CLUSTER_ADDRESS $TRAVEL_LIMIT_MM $SPEED_MM_PER_S $CURRENT_PERCENT $STALL_THRESHOLD
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
maze write-speed-cluster $CLUSTER_ADDRESS 40
maze write-current-cluster $CLUSTER_ADDRESS 50
maze write-target-prism $CLUSTER_ADDRESS $PRISM_ADDRESS 100
maze power-off-cluster $CLUSTER_ADDRESS
```


<a id="orgdcd0707"></a>

# Background

<img src="./documentation/img/ramp.png" width="1920">


<a id="orgd5d651d"></a>

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


<a id="orgc2b3a2e"></a>

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
