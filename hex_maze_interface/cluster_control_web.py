"""Local browser application for operating one hex-maze cluster at a time.

The web server is deliberately bound to the loopback interface.  It is a
desktop application with a browser front end, not a network-facing service.
"""

from __future__ import annotations

import secrets
import socket
import threading
import webbrowser
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cluster_control import (
    DEFAULT_CLUSTER_CONTROL_SETTINGS,
    ClusterControl,
    ClusterControlSettings,
    ClusterState,
)
from .hex_maze_interface import HexMazeInterface, MazeException

STATIC_DIRECTORY = Path(__file__).parent / "static" / "cluster_control"
SESSION_COOKIE_NAME = "hex_maze_cluster_control"


def _load_web_dependencies() -> Any:
    """Import optional web dependencies only when this application is launched."""
    try:
        import fastapi
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install choice
        raise RuntimeError(
            "The Cluster Control application is not installed. "
            "Install 'hex-maze-interface[cluster-control]'."
        ) from exc
    return fastapi, uvicorn


def _state_payload(state: ClusterState) -> dict[str, object]:
    return {
        "positions_mm": list(state.positions_mm),
        "homed": list(state.homed),
        "home_outcomes": [outcome.name.lower() for outcome in state.home_outcomes],
        "diagnostics": [
            {
                "communicating": diagnostic.communicating,
                "communication_failure_latched": diagnostic.communication_failure_latched,
                "reset_latched": diagnostic.reset_latched,
                "driver_error_latched": diagnostic.driver_error_latched,
                "charge_pump_undervoltage_latched": diagnostic.charge_pump_undervoltage_latched,
                "recovery_attempted_latched": diagnostic.recovery_attempted_latched,
                "recovery_failed_latched": diagnostic.recovery_failed_latched,
                "mirror_resync_required": diagnostic.mirror_resync_required,
                "stallguard": diagnostic.stallguard,
                "over_temperature_warning": diagnostic.over_temperature_warning,
                "over_temperature_shutdown": diagnostic.over_temperature_shutdown,
                "short_to_ground_a": diagnostic.short_to_ground_a,
                "short_to_ground_b": diagnostic.short_to_ground_b,
                "open_load_a": diagnostic.open_load_a,
                "open_load_b": diagnostic.open_load_b,
                "standstill": diagnostic.standstill,
                "stall_guard_result": diagnostic.stall_guard_result,
                "current_scale": diagnostic.current_scale,
                "last_home_travel_mm": diagnostic.last_home_travel_mm,
            }
            for diagnostic in state.diagnostics or ()
        ],
        "controller_parameters": {
            "start_velocity": state.controller_parameters.start_velocity,
            "stop_velocity": state.controller_parameters.stop_velocity,
            "first_velocity": state.controller_parameters.first_velocity,
            "max_velocity": state.controller_parameters.max_velocity,
            "first_acceleration": state.controller_parameters.first_acceleration,
            "max_acceleration": state.controller_parameters.max_acceleration,
            "max_deceleration": state.controller_parameters.max_deceleration,
            "first_deceleration": state.controller_parameters.first_deceleration,
        },
    }


def _parse_integer(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MazeException(f"{name.replace('_', ' ')} must be an integer")
    return value


def _parse_positions(payload: dict[str, object]) -> tuple[int, ...]:
    values = payload.get("positions_mm")
    if not isinstance(values, list) or any(
        isinstance(value, bool) or not isinstance(value, int) for value in values
    ):
        raise MazeException("positions_mm must be a list of integers")
    return tuple(values)


@dataclass(slots=True)
class _ControlService:
    """Serialize browser requests to one interface instance at a time."""

    settings: ClusterControlSettings
    interface_factory: Callable[[], HexMazeInterface]
    control: ClusterControl | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def connect(self, cluster_address: int) -> ClusterState:
        with self.lock:
            control = ClusterControl(
                self.interface_factory(), cluster_address, settings=self.settings
            )
            state = control.connect()
            self.control = control
            return state

    def require_control(self) -> ClusterControl:
        if self.control is None:
            raise MazeException("connect to a cluster first")
        return self.control

    def read_state(self) -> ClusterState:
        with self.lock:
            return self.require_control().read_state()

    def read_positions(self) -> tuple[int, ...]:
        with self.lock:
            return self.require_control().read_positions()

    def set_max_velocity(self, max_velocity_mm_s: int) -> ClusterState:
        with self.lock:
            return self.require_control().set_max_velocity(max_velocity_mm_s)

    def home_all(self) -> ClusterState:
        with self.lock:
            return self.require_control().home_all()

    def move_all(self, positions_mm: tuple[int, ...]) -> ClusterState:
        with self.lock:
            control = self.require_control()
            control.move_all(positions_mm)
            return control.read_state()

    def pause(self) -> ClusterState:
        with self.lock:
            control = self.require_control()
            control.pause()
            return control.read_state()

    def power_off(self) -> ClusterState:
        with self.lock:
            control = self.require_control()
            control.power_off()
            return control.read_state()


def create_app(
    *,
    session_token: str | None = None,
    settings: ClusterControlSettings = DEFAULT_CLUSTER_CONTROL_SETTINGS,
    interface_factory: Callable[[], HexMazeInterface] = HexMazeInterface,
    launch_url: str | None = None,
    shutdown_callback: Callable[[], None] | None = None,
) -> Any:
    """Create the optional FastAPI application without changing the core API."""
    fastapi, _ = _load_web_dependencies()
    token = session_token or secrets.token_urlsafe(32)
    service = _ControlService(settings=settings, interface_factory=interface_factory)

    @asynccontextmanager
    async def lifespan(_: Any) -> Any:
        if launch_url is not None:
            threading.Thread(target=webbrowser.open, args=(launch_url,), daemon=True).start()
        yield

    app = fastapi.FastAPI(
        title="Hex Maze Cluster Control", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.service = service

    def session_is_valid(cookie_value: str | None) -> bool:
        return secrets.compare_digest(cookie_value or "", token)

    async def require_session(
        session_cookie: str | None = fastapi.Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> None:
        if not session_is_valid(session_cookie):
            raise fastapi.HTTPException(
                status_code=403, detail="This Cluster Control session is not authorized"
            )

    @app.exception_handler(MazeException)
    async def maze_exception_handler(_: Any, exc: MazeException) -> Any:
        return fastapi.responses.JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/")
    async def index(
        token: str | None = None,
        session_cookie: str | None = fastapi.Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> Any:
        if token is not None and secrets.compare_digest(token, session_token_value):
            response = fastapi.responses.RedirectResponse(url="/", status_code=303)
            response.set_cookie(
                SESSION_COOKIE_NAME,
                session_token_value,
                httponly=True,
                samesite="strict",
            )
            return response
        if not session_is_valid(session_cookie):
            raise fastapi.HTTPException(
                status_code=403, detail="Open Cluster Control from its launcher"
            )
        return fastapi.responses.FileResponse(STATIC_DIRECTORY / "index.html")

    @app.get("/static/{asset_name}")
    async def static_asset(asset_name: str) -> Any:
        if asset_name not in {"cluster-control.css", "cluster-control.js"}:
            raise fastapi.HTTPException(status_code=404, detail="Not found")
        return fastapi.responses.FileResponse(STATIC_DIRECTORY / asset_name)

    @app.get("/api/state", dependencies=[fastapi.Depends(require_session)])
    async def read_state() -> dict[str, object]:
        return {"state": _state_payload(service.read_state())}

    @app.get("/api/positions", dependencies=[fastapi.Depends(require_session)])
    async def read_positions() -> dict[str, object]:
        return {"positions_mm": list(service.read_positions())}

    @app.post("/api/connect", dependencies=[fastapi.Depends(require_session)])
    async def connect(payload: dict[str, object]) -> dict[str, object]:
        cluster_address = _parse_integer(payload, "cluster_address")
        return {"state": _state_payload(service.connect(cluster_address))}

    @app.post("/api/max-velocity", dependencies=[fastapi.Depends(require_session)])
    async def set_max_velocity(payload: dict[str, object]) -> dict[str, object]:
        max_velocity_mm_s = _parse_integer(payload, "max_velocity_mm_s")
        return {"state": _state_payload(service.set_max_velocity(max_velocity_mm_s))}

    @app.post("/api/home", dependencies=[fastapi.Depends(require_session)])
    async def home_all() -> dict[str, object]:
        return {"state": _state_payload(service.home_all())}

    @app.post("/api/move", dependencies=[fastapi.Depends(require_session)])
    async def move_all(payload: dict[str, object]) -> dict[str, object]:
        return {"state": _state_payload(service.move_all(_parse_positions(payload)))}

    @app.post("/api/pause", dependencies=[fastapi.Depends(require_session)])
    async def pause() -> dict[str, object]:
        return {"state": _state_payload(service.pause())}

    @app.post("/api/power-off", dependencies=[fastapi.Depends(require_session)])
    async def power_off() -> dict[str, object]:
        return {"state": _state_payload(service.power_off())}

    @app.post("/api/quit", dependencies=[fastapi.Depends(require_session)])
    async def quit_application() -> dict[str, bool]:
        if shutdown_callback is not None:
            threading.Timer(0.1, shutdown_callback).start()
        return {"ok": True}

    session_token_value = token
    return app


def _find_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    """Launch Cluster Control in the user's default web browser."""
    _, uvicorn = _load_web_dependencies()
    port = _find_loopback_port()
    token = secrets.token_urlsafe(32)
    launch_url = f"http://127.0.0.1:{port}/?token={token}"
    server_holder: dict[str, Any] = {}

    def shutdown() -> None:
        server_holder["server"].should_exit = True

    app = create_app(
        session_token=token,
        launch_url=launch_url,
        shutdown_callback=shutdown,
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_holder["server"] = server
    server.run()


if __name__ == "__main__":
    main()
