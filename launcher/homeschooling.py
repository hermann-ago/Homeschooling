"""Start, stop and inspect the Homeschooling home server.

    python launcher/homeschooling.py start [--port 8000] [--no-browser]
    python launcher/homeschooling.py stop
    python launcher/homeschooling.py status
    python launcher/homeschooling.py open
    python launcher/homeschooling.py pair-agent [--name "Codex"]

The launcher records the exact process it started (PID, creation time,
command line and a per-instance token) under %LOCALAPPDATA%\\Homeschooling\\run.
``stop`` only ever stops that recorded process: it never kills whatever
happens to be using a port. Ending a lesson does not stop the server; other
devices keep using it until a parent stops it here.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
sys.path.insert(0, str(BACKEND))

from config import HostConfig  # noqa: E402

try:
    import psutil
except ImportError:  # pragma: no cover - installed by requirements.txt
    psutil = None


def run_dir(config: HostConfig) -> Path:
    path = config.dir / "run"
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_path(config) -> Path:
    return run_dir(config) / "server.json"


def lan_addresses() -> list[str]:
    addresses = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))  # no packets are sent
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in addresses if not a.startswith("127."))


def _process(record: dict):
    """The recorded process, only if it is still the same process we started."""
    if not psutil or not record:
        return None
    try:
        process = psutil.Process(record["pid"])
        if abs(process.create_time() - record["create_time"]) > 1:
            return None
        if "main:app" not in " ".join(process.cmdline()):
            return None
        return process
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _request(url: str, payload: dict | None = None, timeout: float = 5):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                     method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def _read_record(config) -> dict | None:
    path = record_path(config)
    return json.loads(path.read_text()) if path.exists() else None


def _port_holder(port: int):
    if not psutil:
        return None
    for connection in psutil.net_connections(kind="tcp"):
        if connection.laddr and connection.laddr.port == port and connection.status == psutil.CONN_LISTEN:
            return connection.pid
    return None


def build_frontend():
    npm = "npm.cmd" if os.name == "nt" else "npm"
    print("Building the app interface (first run only)…")
    subprocess.run([npm, "ci", "--legacy-peer-deps"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def start(config: HostConfig, port: int, open_browser: bool):
    record = _read_record(config)
    if _process(record):
        print(f"The home server is already running (PID {record['pid']}).")
        announce(record["port"], open_browser)
        return 0
    if record:
        record_path(config).unlink(missing_ok=True)  # stale record from an earlier run
    holder = _port_holder(port)
    if holder:
        print(f"Port {port} is already used by another program (PID {holder}). It was not stopped.")
        print("Close that program or start with --port <another port>.")
        return 1
    if not (FRONTEND / "dist" / "index.html").exists():
        build_frontend()
    log_dir = config.dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "server.log", "ab")
    command = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(command, cwd=BACKEND, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                               creationflags=flags, start_new_session=os.name != "nt")
    for _ in range(120):
        time.sleep(0.5)
        if process.poll() is not None:
            print(f"The server stopped while starting. See {log_dir / 'server.log'}.")
            return 1
        try:
            _request(f"http://127.0.0.1:{port}/api/health", timeout=2)
            break
        except (urllib.error.URLError, OSError):
            continue
    else:
        print("The server did not answer within 60 seconds; it is still starting. Check status shortly.")
    instance = json.loads((run_dir(config) / "instance.json").read_text())
    created = psutil.Process(process.pid).create_time() if psutil else time.time()
    record = {"pid": process.pid, "create_time": created, "port": port, "command": command,
              "instance_token": instance["token"], "started_at": time.time()}
    path = record_path(config)
    path.write_text(json.dumps(record))
    if os.name != "nt":
        os.chmod(path, 0o600)
    config.update(port=port)
    announce(port, open_browser)
    return 0


def announce(port: int, open_browser: bool):
    print("\nHomeschooling is running.")
    print(f"  On this computer:   http://localhost:{port}")
    for address in lan_addresses():
        print(f"  Other home devices: http://{address}:{port}")
    print("Keep this computer awake and on the home network while others use it.")
    print("Nothing is exposed to the internet; no router or tunnel settings are needed.")
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")


def stop(config: HostConfig):
    record = _read_record(config)
    process = _process(record)
    if not process:
        record_path(config).unlink(missing_ok=True)
        print("No recorded home server is running.")
        return 0
    try:
        result = _request(f"http://127.0.0.1:{record['port']}/api/host/shutdown",
                          {"instance_token": record["instance_token"]}, timeout=30)
        print("Stopping; every saved change is already in the database." if result.get("stopping") else
              f"Stop request answered: {result}")
    except (urllib.error.URLError, OSError) as error:
        print(f"Graceful stop was not acknowledged ({error}); stopping the recorded process.")
    try:
        process.wait(timeout=20)
    except psutil.TimeoutExpired:
        process.terminate()  # the verified process we started, never a port lookup
        process.wait(timeout=10)
    record_path(config).unlink(missing_ok=True)
    print("The home server has stopped. A backup was written to the Drive folder's Backups.")
    return 0


def status(config: HostConfig):
    record = _read_record(config)
    if not _process(record):
        print("Stopped.")
        return 1
    print(f"Running (PID {record['pid']}) on port {record['port']}.")
    try:
        sync = _request(f"http://127.0.0.1:{record['port']}/api/health")
        print(f"Health: {sync.get('status')}")
    except (urllib.error.URLError, OSError) as error:
        print(f"Not answering: {error}")
    return 0


def pair_agent(config: HostConfig, name: str):
    record = _read_record(config)
    if not _process(record):
        print("Start the home server first.")
        return 1
    result = _request(f"http://127.0.0.1:{record['port']}/api/pairing/agent", {"name": name})
    sys.path.insert(0, str(BACKEND))
    from security.secrets import write_secret
    write_secret(config.secrets_dir / "agent-token.bin", result["token"].encode())
    print(f"Paired '{name}' as the tutor bridge. Its credential is stored for this Windows user only.")
    print(f"MCP bridge server address: http://127.0.0.1:{record['port']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Homeschooling home server")
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--port", type=int)
    start_parser.add_argument("--no-browser", action="store_true")
    commands.add_parser("stop")
    commands.add_parser("status")
    commands.add_parser("open")
    commands.add_parser("build")
    agent = commands.add_parser("pair-agent")
    agent.add_argument("--name", default="Desktop tutor")
    args = parser.parse_args(argv)
    config = HostConfig()
    if args.command == "start":
        return start(config, args.port or config.get("port"), not args.no_browser)
    if args.command == "stop":
        return stop(config)
    if args.command == "status":
        return status(config)
    if args.command == "open":
        webbrowser.open(f"http://localhost:{config.get('port')}")
        return 0
    if args.command == "build":
        build_frontend()
        return 0
    if args.command == "pair-agent":
        return pair_agent(config, args.name)


if __name__ == "__main__":
    sys.exit(main())
