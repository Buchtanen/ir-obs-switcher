"""Smoke a built EXE/wheel on a disposable port/config with OBS/commentary disabled.

Usage: python scripts/qa_studio_package.py dist/irswitchd.exe
       python scripts/qa_studio_package.py dist/irswitch-1.3.0-py3-none-any.whl
Never reuses the user's INI, port, definition store or OBS endpoint.
"""

from __future__ import annotations

import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    executable = Path(sys.argv[1]).resolve()
    root = Path(__file__).resolve().parents[1]
    directory = Path(tempfile.mkdtemp(prefix="studio-package-", dir=root / "build"))
    command = [str(executable)]
    if executable.suffix == ".whl":
        package = directory / "wheel"
        with zipfile.ZipFile(executable) as archive:
            archive.extractall(package)
        expected = {
            p.relative_to(root / "src/irswitch/web/studio")
            for p in (root / "src/irswitch/web/studio").rglob("*")
            if p.is_file()
        }
        actual = {
            p.relative_to(package / "irswitch/web/studio")
            for p in (package / "irswitch/web/studio").rglob("*")
            if p.is_file()
        }
        assert actual == expected, "Wheel contains stale/missing Studio assets; clean build/lib"
        for source in (root / "src/irswitch/web/studio").rglob("*"):
            if source.is_file():
                assert (
                    package / source.relative_to(root / "src")
                ).read_bytes() == source.read_bytes()
        command = [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; p=sys.argv.pop(1); sys.path.insert(0,p); "
            "import irswitch; assert Path(irswitch.__file__).is_relative_to(Path(p)); "
            "from irswitch.main import main; main()",
            str(package),
        ]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = directory / "config.ini"
    config.write_text(
        f"""[app]
http_host = 127.0.0.1
http_port = {port}
log_level = WARNING
log_file = {directory.as_posix()}/service.log
notifications_enabled = false
[iracing]
poll_hz = 1
[obs]
ws_url = ws://127.0.0.1:1
password = studio-smoke-disabled
[switching]
autoswitch_default = false
debounce_ms = 900
cooldown_ms = 1000
override_seconds = 120
safe_scene = StudioFixture
[scenes]
IDLE = StudioFixture
GARAGE = StudioFixture
RACE = StudioFixture
REPLAY = StudioFixture
[overlay]
enabled = false
[commentary]
enabled = false
""",
        encoding="utf-8",
    )
    base = f"http://127.0.0.1:{port}"
    original_config = config.read_bytes()

    def get(path):
        with urlopen(base + path, timeout=5) as response:
            raw = response.read()
            return json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw

    def post(path, body):
        request = Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-Requested-With": "irswitch"},
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def start():
        proc = subprocess.Popen(
            [*command, "--config", str(config), "--mock"],
            cwd=directory,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"EXE exited {proc.returncode}; see {directory}")
            try:
                get("/health")
                return proc
            except OSError:
                time.sleep(0.2)
        proc.terminate()
        proc.wait(timeout=5)
        raise AssertionError(f"EXE startup timeout; see {directory}")

    def stop(proc):
        try:
            post("/shutdown", {})
            proc.wait(timeout=15)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)

    proc = start()
    try:
        for path in (
            "/studio/",
            "/admin",
            "/config",
            "/commentary",
            "/overlay/",
            "/gr-status",
            "/vr-status",
        ):
            assert get(path), path
        import re

        html = get("/studio/").decode()
        assert html == (root / "src/irswitch/web/studio/index.html").read_text(encoding="utf-8")
        for asset in re.findall(r'(?:src|href)="(/studio/assets/[^"]+)"', html):
            assert get(asset), asset
        state = get("/api/studio/definitions")
        document = state["builtin"]
        story = copy.deepcopy(next(s for s in document["stories"] if s["id"] == "battle_ahead"))
        story["id"] = "studio.package_test"
        document["stories"].append(story)
        saved = post(
            "/api/studio/definitions/save",
            {"document": document, "baseRevision": state["baseRevision"]},
        )
        revision = saved["savedRevision"]
        selected = post(
            "/api/studio/definitions/activate",
            {"revision": revision, "baseRevision": saved["baseRevision"]},
        )
        assert selected["runtime"]["effectiveRevision"] == "builtin"
        assert not any(
            s["id"] == "studio.package_test"
            for s in get("/api/studio/catalog")["narrative"]["stories"]
        )
        replay = post("/api/studio/replay", {"fixture": "narrative_world", "document": document})
        assert any(e["definition_id"] == "studio.package_test" for e in replay["episodes"])
    finally:
        stop(proc)
    proc = start()
    try:
        state = get("/api/studio/definitions")
        assert state["runtime"]["effectiveRevision"] == revision
        assert any(
            s["id"] == "studio.package_test"
            for s in get("/api/studio/catalog")["narrative"]["stories"]
        )
        post(
            "/api/studio/definitions/activate",
            {"revision": "builtin", "baseRevision": state["baseRevision"]},
        )
    finally:
        stop(proc)
    proc = start()
    try:
        assert get("/api/studio/definitions")["runtime"]["effectiveRevision"] == "builtin"
    finally:
        stop(proc)
    assert config.read_bytes() == original_config, "Package restart changed existing configuration"
    print(
        f"PASS packaged {executable.suffix}: assets/legacy routes, save/select, unchanged live catalog/config, startup activation, isolated custom replay, next-startup rollback. Evidence: {directory}"
    )


if __name__ == "__main__":
    main()
