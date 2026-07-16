from __future__ import annotations

import asyncio

import pytest

from hex_maze_interface.hex_maze_interface import ControllerParameters, HomeOutcome


class FakeInterface:
    def __init__(self) -> None:
        self.parameters = ControllerParameters(10, 10, 40, 20, 120, 80, 80, 120)
        self.positions = (0,) * 7
        self.homed = (False,) * 7
        self.outcomes = (HomeOutcome.NONE,) * 7

    def communicating_cluster(self, cluster_address: int) -> bool:
        return cluster_address == 10

    def read_positions_cluster(self, cluster_address: int) -> tuple[int, ...]:
        return self.positions

    def homed_cluster(self, cluster_address: int) -> tuple[bool, ...]:
        return self.homed

    def read_home_outcomes_cluster(self, cluster_address: int) -> tuple[HomeOutcome, ...]:
        return self.outcomes

    def read_controller_parameters_cluster(self, cluster_address: int) -> ControllerParameters:
        return self.parameters

    def write_controller_parameters_cluster(
        self, cluster_address: int, parameters: ControllerParameters
    ) -> bool:
        self.parameters = parameters
        return True

    def home_cluster(self, cluster_address: int, parameters: object) -> bool:
        self.homed = (True,) * 7
        self.outcomes = (HomeOutcome.STALL,) * 7
        return True

    def write_targets_cluster(self, cluster_address: int, positions: tuple[int, ...]) -> bool:
        self.positions = positions
        return True

    def pause_cluster(self, cluster_address: int) -> bool:
        return True

    def power_off_cluster(self, cluster_address: int) -> bool:
        return True


def test_browser_api_uses_local_session_and_public_interface() -> None:
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")
    from hex_maze_interface.cluster_control_web import create_app

    async def exercise_api() -> None:
        app = create_app(session_token="test-token", interface_factory=FakeInterface)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            unauthorized = await client.post("/api/connect", json={"cluster_address": 10})
            assert unauthorized.status_code == 403

            launcher = await client.get("/?token=test-token", follow_redirects=False)
            assert launcher.status_code == 303

            connected = await client.post("/api/connect", json={"cluster_address": 10})
            assert connected.status_code == 200

            velocity = await client.post("/api/max-velocity", json={"max_velocity_mm_s": 40})
            assert velocity.status_code == 200
            assert velocity.json()["state"]["controller_parameters"]["max_velocity"] == 40

            homed = await client.post("/api/home")
            assert homed.status_code == 200

            moved = await client.post(
                "/api/move",
                json={"positions_mm": [10, 20, 30, 40, 50, 60, 70]},
            )
            assert moved.status_code == 200
            assert moved.json()["state"]["positions_mm"] == [10, 20, 30, 40, 50, 60, 70]

    asyncio.run(exercise_api())
