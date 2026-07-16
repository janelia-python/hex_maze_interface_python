from __future__ import annotations

import pytest

from hex_maze_interface.cluster_control import (
    ClusterControl,
    ClusterControlSettings,
    ClusterState,
)
from hex_maze_interface.hex_maze_interface import (
    ControllerParameters,
    HomeOutcome,
    MazeException,
)


class FakeInterface:
    def __init__(self) -> None:
        self.parameters = ControllerParameters(
            start_velocity=10,
            stop_velocity=10,
            first_velocity=50,
            max_velocity=50,
            first_acceleration=120,
            max_acceleration=80,
            max_deceleration=80,
            first_deceleration=120,
        )
        self.positions = (0, 0, 0, 0, 0, 0, 0)
        self.homed = (False, False, False, False, False, False, False)
        self.outcomes = (HomeOutcome.NONE,) * 7
        self.received_targets: tuple[int, ...] | None = None
        self.received_home_parameters = None
        self.paused = False
        self.powered_off = False

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
        self.received_home_parameters = parameters
        self.homed = (True,) * 7
        self.outcomes = (HomeOutcome.STALL,) * 7
        return True

    def write_targets_cluster(self, cluster_address: int, targets: tuple[int, ...]) -> bool:
        self.received_targets = targets
        self.positions = targets
        return True

    def pause_cluster(self, cluster_address: int) -> bool:
        self.paused = True
        return True

    def power_off_cluster(self, cluster_address: int) -> bool:
        self.powered_off = True
        return True


def test_connect_reads_selected_cluster_state() -> None:
    control = ClusterControl(FakeInterface(), 10)

    state = control.connect()

    assert state.positions_mm == (0,) * 7
    assert state.controller_parameters.max_velocity == 50


def test_set_max_velocity_preserves_other_controller_parameters() -> None:
    interface = FakeInterface()
    control = ClusterControl(interface, 10)

    state = control.set_max_velocity(50)

    assert state.controller_parameters.max_velocity == 50
    assert interface.parameters.start_velocity == 10
    assert interface.parameters.first_acceleration == 120


def test_set_max_velocity_rejects_unvalidated_value() -> None:
    control = ClusterControl(FakeInterface(), 10)

    with pytest.raises(MazeException, match="between 10 and 50"):
        control.set_max_velocity(51)


def test_home_uses_fixed_parameters_and_accepts_stall_outcomes() -> None:
    interface = FakeInterface()
    control = ClusterControl(interface, 10)

    state = control.home_all()

    assert control.home_succeeded(state) is True
    assert interface.received_home_parameters.to_tuple() == (100, 10, 43, 0)


@pytest.mark.parametrize(
    "outcome",
    (HomeOutcome.STALL, HomeOutcome.TARGET_REACHED, HomeOutcome.CONFIRMED),
)
def test_home_succeeded_accepts_supported_terminal_outcomes(outcome: HomeOutcome) -> None:
    state = ClusterState(
        positions_mm=(0,) * 7,
        homed=(True,) * 7,
        home_outcomes=(outcome,) * 7,
        controller_parameters=ControllerParameters(),
    )

    assert ClusterControl.home_succeeded(state) is True


def test_home_rereads_positions_after_terminal_outcome() -> None:
    class HomeRefreshInterface(FakeInterface):
        def __init__(self) -> None:
            super().__init__()
            self.position_read_count = 0

        def home_cluster(self, cluster_address: int, parameters: object) -> bool:
            self.received_home_parameters = parameters
            self.homed = (True,) * 7
            self.outcomes = (HomeOutcome.TARGET_REACHED,) * 7
            return True

        def read_positions_cluster(self, cluster_address: int) -> tuple[int, ...]:
            self.position_read_count += 1
            if self.position_read_count == 1:
                return (41,) * 7
            return (0,) * 7

    interface = HomeRefreshInterface()
    state = ClusterControl(interface, 10).home_all()

    assert state.positions_mm == (0,) * 7
    assert interface.position_read_count == 2


def test_move_all_requires_seven_targets_in_the_allowed_range() -> None:
    interface = FakeInterface()
    control = ClusterControl(interface, 10)

    control.move_all((10, 20, 30, 40, 50, 60, 70))

    assert interface.received_targets == (10, 20, 30, 40, 50, 60, 70)
    with pytest.raises(MazeException, match="exactly 7"):
        control.move_all((10, 20))
    with pytest.raises(MazeException, match="between 0 and 550"):
        control.move_all((0, 0, 0, 0, 0, 0, 551))


def test_settings_reject_invalid_limit_order() -> None:
    with pytest.raises(ValueError, match="minimum_position"):
        ClusterControlSettings(minimum_position_mm=20, maximum_position_mm=10)
