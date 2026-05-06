from __future__ import annotations

import json

from click.testing import CliRunner

from hex_maze_interface.cli import cli
from hex_maze_interface.hex_maze_interface import HexMazeInterface, PrismDiagnostics


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


def test_read_prism_diagnostics_cluster_json(monkeypatch) -> None:
    monkeypatch.setattr(
        HexMazeInterface,
        "read_prism_diagnostics_cluster",
        lambda self, cluster_address: (
            (PrismDiagnostics.from_wire(0x05, 0x02, 123, 9, 12),) * HexMazeInterface.PRISM_COUNT
        ),
    )

    result = CliRunner().invoke(cli, ["read-prism-diagnostics-cluster", "10", "--json"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output[0]["communicating"] is True
    assert output[0]["reset_latched"] is True
    assert output[0]["over_temperature_warning"] is True
    assert output[0]["stall_guard_result"] == 123
    assert output[0]["last_home_travel_mm"] == 12


def test_recovery_home_cluster_cli(monkeypatch) -> None:
    calls = []

    def recovery_home_cluster(self, cluster_address, home_parameters):
        calls.append((cluster_address, home_parameters.to_tuple()))
        return True

    monkeypatch.setattr(HexMazeInterface, "recovery_home_cluster", recovery_home_cluster)

    result = CliRunner().invoke(cli, ["recovery-home-cluster", "10", "550", "10", "40", "0"])

    assert result.exit_code == 0
    assert result.output.strip() == "True"
    assert calls == [(10, (550, 10, 40, 0))]


def test_confirm_home_cluster_cli(monkeypatch) -> None:
    calls = []

    def confirm_home_cluster(self, cluster_address):
        calls.append(cluster_address)
        return True

    monkeypatch.setattr(HexMazeInterface, "confirm_home_cluster", confirm_home_cluster)

    result = CliRunner().invoke(cli, ["confirm-home-cluster", "10"])

    assert result.exit_code == 0
    assert result.output.strip() == "True"
    assert calls == [10]
