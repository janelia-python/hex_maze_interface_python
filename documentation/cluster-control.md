# Cluster Control desktop application

Cluster Control is a small browser-based control surface for one cluster at a
time. It is separate from the `maze` command-line interface: it uses the same
public `HexMazeInterface` methods and does not change the interface used by
the seven-cluster maze.

## Operator workflow

1. Connect the computer's Ethernet adapter to the maze network and assign it
   an unused `192.168.10.x` address with subnet mask `255.255.255.0`. Do not
   set a gateway or DNS server on that adapter.
2. Launch **Cluster Control**. It opens in the default browser without using
   the internet.
3. Select the one cluster address to operate (`10` normally means
   `192.168.10.10`), then select **Connect**.
4. Select **Home all**. Motion remains disabled until all seven prisms report
   a successful terminal home outcome.
5. Enter seven target positions in millimetres and select **Move to targets**.

**Pause** stops the selected cluster's motion. **Power off** turns off its
prism power and requires another home before motion can be commanded. The
browser's **Quit** button closes the local controller application.

The current rewrite firmware locks one validated controller profile for every
prism in a cluster. The application displays its maximum velocity readback but
does not offer a setting that firmware will reject. A firmware change is
required before the profile can be adjusted again.

## Validated defaults and limits

The operator app uses the current firmware's validated ordinary-home profile:

- Home: 100 mm travel limit, 10 mm/s maximum velocity, 43% run current, and
  stall threshold 0.
- Position input: 0–550 mm, matching the firmware clamp.

Ordinary homing is fixed-travel: the browser shows its successful
`target_reached` firmware outcome as **fixed-travel complete (homed)**. The
firmware zeros the position on that result. A refresh is still available for
inspection, but the application also performs a final state read after Home
all so Current displays the zeroed position without needing a manual refresh.

Mechanical safe travel can be smaller than the firmware clamp. Validate the
fixture-specific range before changing `ClusterControlSettings`.

## Pixi installation for managed computers

Pixi is the recommended installation path for developers, technicians, and
lab-managed computers. It creates the pinned environment described by
`pixi.lock`, so Windows, macOS, and Linux use the same application
dependencies:

```sh
git clone https://github.com/janelia-python/hex_maze_interface_python.git
cd hex_maze_interface_python
pixi install
pixi run cluster-control
```

`pixi run cluster-control` starts the local application and opens the browser
UI. A technician can make a desktop shortcut that runs this command from the
checked-out repository. Use `git pull` followed by `pixi install` when
updating the managed installation.

Git is not required on an operator computer. After a commit is pushed to
GitHub, use **Code → Download ZIP**, extract it, open a terminal in the
extracted directory, and run the same `pixi install` and
`pixi run cluster-control` commands. To update that kind of installation,
download and extract a fresh ZIP.

## Python development installation

The optional application dependencies do not affect existing users of the
Python API or the `maze` CLI:

```sh
python -m pip install 'hex-maze-interface[cluster-control]'
cluster-control
```

The program starts an HTTP server only on `127.0.0.1` and opens a
per-launch, cookie-protected local URL. It never listens on the Ethernet maze
network, and it does not require an internet connection.

## Native release artifacts

The repository workflow `.github/workflows/build-cluster-control.yml` creates
native artifacts for Windows, macOS, and Linux. Trigger it from GitHub's
**Actions** tab and download the artifact matching the operator's computer.

- Windows: extract the ZIP and launch `ClusterControl.exe`.
- macOS: extract `ClusterControl.app`, move it to Applications if desired, and
  open it. An unsigned build may require Control-click → Open until the
  release is signed and notarized.
- Linux: extract the archive, mark `ClusterControl` executable if needed, and
  launch it from the desktop or terminal.

For routine lab use, sign the Windows executable and sign/notarize the macOS
application. That removes the operating-system trust warnings; it does not
change the maze-control protocol.
