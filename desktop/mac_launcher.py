from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import uvicorn
import webview


APP_NAME = "Paper Local"
WINDOW_SIZE = (1320, 860)


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def _prepare_import_path(resource_root: Path) -> None:
    backend_path = resource_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return int(s.getsockname()[1])


def _configure_environment(resource_root: Path, port: int) -> None:
    app_data = Path.home() / "Library" / "Application Support" / "PaperLocal"
    app_data.mkdir(parents=True, exist_ok=True)

    os.environ["APP_PROJECT_ROOT"] = str(resource_root)
    os.environ["APP_FRONTEND_DIST_DIR"] = str(resource_root / "frontend" / "dist")
    os.environ["APP_STORAGE_DIR"] = str(app_data / "storage")
    os.environ["APP_DB_PATH"] = str(app_data / "storage" / "app.db")
    os.environ["APP_ATTACHMENTS_DIR"] = str(app_data / "storage" / "attachments")
    os.environ["APP_BACKUPS_DIR"] = str(app_data / "storage" / "backups")
    os.environ["APP_HOST"] = "127.0.0.1"
    os.environ["APP_PORT"] = str(port)


def _start_server(port: int):
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def _wait_for_server(port: int, timeout_seconds: float = 20.0) -> None:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Backend failed to start in time")


def main() -> None:
    resource_root = _resource_root()
    _prepare_import_path(resource_root)
    port = _find_free_port()
    _configure_environment(resource_root, port)

    server, thread = _start_server(port)
    _wait_for_server(port)

    window = webview.create_window(
        APP_NAME,
        url=f"http://127.0.0.1:{port}/",
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=(980, 680),
    )

    def on_closed() -> None:
        server.should_exit = True

    window.events.closed += on_closed
    webview.start(debug=False)

    thread.join(timeout=3.0)


if __name__ == "__main__":
    main()
