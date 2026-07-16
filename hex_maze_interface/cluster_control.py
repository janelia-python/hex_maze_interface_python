"""Small, safety-oriented control surface for one seven-prism cluster.

This module intentionally uses the public :class:`HexMazeInterface` methods
only.  It is independent of any GUI toolkit so both the desktop application
and automated tests use the same validation and command sequence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from .hex_maze_interface import (
    ControllerParameters,
    HexMazeInterface,
    HomeOutcome,
    HomeParameters,
    MazeException,
)


@dataclass(frozen=True, slots=True)
class ClusterControlSettings:
    """Limits and fixed homing parameters for the operator application.

    The current rewrite firmware locks the normal motion profile to values
    validated on the full rig.  The maximum-velocity limits remain available
    for the programmatic helper, for firmware revisions that permit tuning,
    but are not exposed by the operator UI.  Change the fixed home parameters
    only after validating the corresponding values on the physical rig.
    """

    minimum_position_mm: int = 0
    maximum_position_mm: int = 550
    minimum_max_velocity_mm_s: int = 10
    maximum_max_velocity_mm_s: int = 50
    home_parameters: HomeParameters = field(
        default_factory=lambda: HomeParameters(
            travel_limit=100,
            max_velocity=10,
            run_current=43,
            stall_threshold=0,
        )
    )
    home_timeout_s: float = 30.0
    home_poll_interval_s: float = 0.25

    def __post_init__(self) -> None:
        if self.minimum_position_mm > self.maximum_position_mm:
            raise ValueError("minimum_position_mm must not exceed maximum_position_mm")
        if self.minimum_max_velocity_mm_s > self.maximum_max_velocity_mm_s:
            raise ValueError("minimum_max_velocity_mm_s must not exceed maximum_max_velocity_mm_s")
        if self.home_timeout_s <= 0:
            raise ValueError("home_timeout_s must be positive")
        if self.home_poll_interval_s <= 0:
            raise ValueError("home_poll_interval_s must be positive")


DEFAULT_CLUSTER_CONTROL_SETTINGS = ClusterControlSettings()


@dataclass(frozen=True, slots=True)
class ClusterState:
    """The status shown by the single-cluster operator application."""

    positions_mm: tuple[int, ...]
    homed: tuple[bool, ...]
    home_outcomes: tuple[HomeOutcome, ...]
    controller_parameters: ControllerParameters


class ClusterControl:
    """Validate and execute the limited operator workflow for one cluster."""

    def __init__(
        self,
        hmi: HexMazeInterface,
        cluster_address: int,
        *,
        settings: ClusterControlSettings = DEFAULT_CLUSTER_CONTROL_SETTINGS,
        sleep_fn: Any = time.sleep,
        monotonic_fn: Any = time.monotonic,
    ) -> None:
        HexMazeInterface._validate_cluster_address(cluster_address)
        self._hmi = hmi
        self.cluster_address = cluster_address
        self.settings = settings
        self._sleep_fn = sleep_fn
        self._monotonic_fn = monotonic_fn

    def connect(self) -> ClusterState:
        """Confirm that the selected cluster is reachable and read its state."""
        if not self._hmi.communicating_cluster(self.cluster_address):
            raise MazeException(f"cluster {self.cluster_address} did not respond over Ethernet")
        return self.read_state()

    def read_state(self) -> ClusterState:
        """Read all status that the GUI presents to the operator."""
        positions_mm = tuple(self._hmi.read_positions_cluster(self.cluster_address))
        homed = tuple(bool(value) for value in self._hmi.homed_cluster(self.cluster_address))
        home_outcomes = tuple(self._hmi.read_home_outcomes_cluster(self.cluster_address))
        controller_parameters = self._hmi.read_controller_parameters_cluster(self.cluster_address)
        return ClusterState(
            positions_mm=positions_mm,
            homed=homed,
            home_outcomes=home_outcomes,
            controller_parameters=controller_parameters,
        )

    @staticmethod
    def home_succeeded(state: ClusterState) -> bool:
        """Return whether every prism reports a successful home outcome.

        Current firmware completes ordinary homing through its bounded,
        fixed-travel target and reports ``TARGET_REACHED``.  Earlier firmware
        may report ``STALL``, and an explicit physical confirmation reports
        ``CONFIRMED``.  The terminal outcomes are therefore authoritative for
        enabling motion.
        """
        return all(
            outcome
            in (
                HomeOutcome.STALL,
                HomeOutcome.TARGET_REACHED,
                HomeOutcome.CONFIRMED,
            )
            for outcome in state.home_outcomes
        )

    def set_max_velocity(self, max_velocity_mm_s: int) -> ClusterState:
        """Set the shared cluster maximum velocity and verify its readback."""
        self._validate_max_velocity(max_velocity_mm_s)
        current = self._hmi.read_controller_parameters_cluster(self.cluster_address)
        requested = replace(current, max_velocity=max_velocity_mm_s)
        if not self._hmi.write_controller_parameters_cluster(self.cluster_address, requested):
            raise MazeException("controller-parameter write failed")

        actual = self._hmi.read_controller_parameters_cluster(self.cluster_address)
        if actual.max_velocity != max_velocity_mm_s:
            raise MazeException(
                "controller maximum velocity was not accepted: "
                f"requested {max_velocity_mm_s}, read back {actual.max_velocity}"
            )
        return self.read_state()

    def home_all(self) -> ClusterState:
        """Start homing all prisms and wait for a terminal outcome."""
        parameters = HomeParameters(*self.settings.home_parameters.to_tuple())
        if not self._hmi.home_cluster(self.cluster_address, parameters):
            raise MazeException("home command was not accepted")

        deadline = self._monotonic_fn() + self.settings.home_timeout_s
        last_state = self.read_state()
        while True:
            if self.home_succeeded(last_state):
                # Firmware zeroes positions immediately before publishing its
                # terminal outcome.  Read once more so a position snapshot
                # taken just before that transition is never returned to the
                # browser as the completed-home state.
                return self.read_state()
            if any(outcome == HomeOutcome.FAILED for outcome in last_state.home_outcomes):
                raise MazeException(self._home_error_message(last_state))
            if self._monotonic_fn() >= deadline:
                raise MazeException(
                    "homing did not complete before the "
                    f"{self.settings.home_timeout_s:g} s timeout; "
                    f"last outcomes: {self._home_outcomes_text(last_state)}"
                )
            self._sleep_fn(self.settings.home_poll_interval_s)
            last_state = self.read_state()

    def move_all(self, positions_mm: Any) -> None:
        """Send all seven target positions after validating the operator input."""
        positions = self._validate_positions(positions_mm)
        if not self._hmi.write_targets_cluster(self.cluster_address, positions):
            raise MazeException("target-position write failed")

    def pause(self) -> None:
        """Immediately pause every prism in the selected cluster."""
        if not self._hmi.pause_cluster(self.cluster_address):
            raise MazeException("pause command was not accepted")

    def power_off(self) -> None:
        """Turn off the selected cluster's prism power."""
        if not self._hmi.power_off_cluster(self.cluster_address):
            raise MazeException("power-off command was not accepted")

    def _validate_max_velocity(self, value: int) -> None:
        if not isinstance(value, int):
            raise MazeException("maximum velocity must be an integer")
        if not (
            self.settings.minimum_max_velocity_mm_s
            <= value
            <= self.settings.maximum_max_velocity_mm_s
        ):
            raise MazeException(
                "maximum velocity must be between "
                f"{self.settings.minimum_max_velocity_mm_s} and "
                f"{self.settings.maximum_max_velocity_mm_s} mm/s"
            )

    def _validate_positions(self, positions_mm: Any) -> tuple[int, ...]:
        try:
            positions = tuple(positions_mm)
        except TypeError as exc:
            raise MazeException("target positions must be iterable") from exc
        if len(positions) != HexMazeInterface.PRISM_COUNT:
            raise MazeException(
                f"exactly {HexMazeInterface.PRISM_COUNT} target positions are required"
            )
        for prism_index, position_mm in enumerate(positions, start=1):
            if not isinstance(position_mm, int):
                raise MazeException(f"prism {prism_index} target position must be an integer")
            if not (
                self.settings.minimum_position_mm
                <= position_mm
                <= self.settings.maximum_position_mm
            ):
                raise MazeException(
                    f"prism {prism_index} target must be between "
                    f"{self.settings.minimum_position_mm} and "
                    f"{self.settings.maximum_position_mm} mm"
                )
        return positions

    @staticmethod
    def _home_outcomes_text(state: ClusterState) -> str:
        return ", ".join(outcome.name.lower() for outcome in state.home_outcomes)

    def _home_error_message(self, state: ClusterState) -> str:
        return f"one or more prisms failed to home: {self._home_outcomes_text(state)}"
