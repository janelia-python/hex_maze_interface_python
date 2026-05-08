# Hardware Test Runners

This directory contains live-hardware debug, smoke, and regression runners.
They are intentionally kept out of the installable `hex_maze_interface` package
and should be run explicitly from a checked-out repository.

From the repository root, run a script with Pixi, for example:

```sh
pixi run python hardware_tests/hardware_smoke_test.py --clusters 10
```

These scripts can command real prism motion. Keep using the superproject
Makefile targets for the desk and full-rig workflows unless a specific debug
task needs a script directly.
