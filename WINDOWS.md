# Running Cluster Control on Windows

This procedure uses Pixi to install the application in a private environment.
It does not require Python, Git, Git Bash, or administrator access after Pixi
has been installed.

## One-time setup

1. Install Pixi from <https://pixi.sh/>.  Close and reopen any Command Prompt
   window after the installer finishes so `pixi` is available on `PATH`.
2. Download the lab's released source ZIP and extract it to a normal folder.
   Do not try to run the application from inside the ZIP archive.
3. Connect the USB Ethernet adapter to the test maze and set that adapter's
   IPv4 address to an unused address on the controller subnet, for example
   `192.168.10.1` with subnet mask `255.255.255.0`.  Do not set a gateway.

## Start the application

Double-click [`Start Cluster Control.cmd`](Start%20Cluster%20Control.cmd).
The first run downloads the locked Windows environment and its supporting
packages. Later runs reuse it.
The browser opens automatically; select the controller's cluster address
(normally `10`) and click **Connect**.

If the launcher reports that Pixi is not found, open a new Command Prompt after
installing Pixi, or use the Pixi installer to add it to the current user's
`PATH`.

## Creating the ZIP for a collaborator

From a clean, committed checkout on a development machine, run:

```sh
pixi run archive
```

This creates `../hex_maze_interface_python.zip`.  Upload that ZIP as a GitHub
release asset or provide it directly.  The collaborator only needs the ZIP,
Pixi, their Ethernet adapter, and the launcher above.
