from __future__ import annotations

import json

from click.testing import CliRunner

from hex_maze_interface.cli import cli
from hex_maze_interface.hex_maze_interface import HexMazeInterface


def test_discover_clusters_json(monkeypatch) -> None:
    monkeypatch.setattr(
        HexMazeInterface,
        "discover_cluster_addresses",
        lambda self: [10, 11],
    )

    result = CliRunner().invoke(cli, ["discover-clusters", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [10, 11]


def test_verify_cluster_json(monkeypatch) -> None:
    monkeypatch.setattr(
        HexMazeInterface,
        "verify_cluster",
        lambda self, cluster_address: {
            "cluster_address": cluster_address,
            "ok": True,
            "checks": {"communicating": True},
        },
    )

    result = CliRunner().invoke(cli, ["verify-cluster", "10", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["ok"] is True


def test_global_timeout_option_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(
        HexMazeInterface, "communicating_cluster", lambda self, cluster_address: True
    )

    result = CliRunner().invoke(cli, ["--timeout", "0.25", "communicating-cluster", "10"])

    assert result.exit_code == 0
    assert result.output.strip() == "True"
