- [About](#org75a1d89)
- [Example Usage](#orge5e5575)
- [Installation](#org9ee6662)
- [Development](#org444e556)

    <!-- This file is generated automatically from metadata -->
    <!-- File edits may be overwritten! -->


<a id="org75a1d89"></a>

# About

```markdown
- Python Package Name: hex_maze_interface
- Description: Python interface to the Voigts lab hex maze.
- Version: 2.2.0
- Python Version: 3.11
- Release Date: 2025-05-14
- Creation Date: 2024-01-14
- License: BSD-3-Clause
- URL: https://github.com/janelia-python/hex_maze_interface_python
- Author: Peter Polidoro
- Email: peter@polidoro.io
- Copyright: 2025 Howard Hughes Medical Institute
- References:
  - https://github.com/janelia-kicad/prism-pcb
  - https://github.com/janelia-kicad/cluster-pcb
  - https://github.com/janelia-arduino/ClusterController
- Dependencies:
  - click
  - python3-nmap
```


<a id="orge5e5575"></a>

# Example Usage


## Python

```python
from hex_maze_interface import HexMazeInterface, MazeException
hmi = HexMazeInterface()
cluster_address = 10
hmi.check_all()
hmi.beep_all(duration_ms=100)
hmi.power_on_all()
hmi.home_all()
actual_positions = hmi.read_actual_positions(cluster_address)
hmi.pause_all()
hmi.write_target_positions(cluster_address, (10, 20, 30, 40, 50, 60, 70))
hmi.resume_all(c)
actual_positions = hmi.read_actual_positions(cluster_address)
hmi.power_off_all()
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
  bad-cmd
  beep
  beep-all
  check
  check-all
  discover
  home
  home-all
  led-off
  led-on
  led-on-then-off
  measure
  no-cmd
  pause
  pause-all
  power-off
  power-off-all
  power-on
  power-on-all
  read-actual-positions
  reset
  resume
  resume-all
  write-target-positions
```


### Example

```sh
CLUSTER_ADDRESS=10
maze check-all
maze beep-all 100
maze power-on-all
maze home-all
maze read-actual-positions $CLUSTER_ADDRESS
maze pause-all
maze write-target-positions $CLUSTER_ADDRESS 10 20 30 40 50 60 70
maze resume-all
maze read-actual-positions $CLUSTER_ADDRESS
maze power-off-all
```


<a id="org9ee6662"></a>

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


<a id="org444e556"></a>

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
