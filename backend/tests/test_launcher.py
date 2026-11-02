import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "launcher"))

import homeschooling as launcher  # noqa: E402


def test_server_runs_as_console_python_even_from_a_windowless_launcher(monkeypatch):
    scripts = Path(r"C:\home\backend\venv\Scripts")
    monkeypatch.setattr(sys, "executable", str(scripts / "pythonw.exe"))
    assert launcher.server_python() == scripts / "python.exe"
    monkeypatch.setattr(sys, "executable", str(scripts / "python.exe"))
    assert launcher.server_python() == scripts / "python.exe"


def test_autostart_starts_windowless_without_opening_a_browser(monkeypatch):
    scripts = Path(r"C:\home\backend\venv\Scripts")
    monkeypatch.setattr(sys, "executable", str(scripts / "python.exe"))
    command = launcher.autostart_command()
    assert command.startswith(f'"{scripts / "pythonw.exe"}" "')
    assert f'"{Path(launcher.__file__).resolve()}"' in command
    assert command.endswith(" start --no-browser")


def test_secure_addresses_are_announced_with_windows_console_safe_text(monkeypatch, capsys):
    monkeypatch.setattr(launcher, 'lan_addresses', lambda: ['192.168.15.5'])
    launcher.announce(8000, False, {'enabled': True, 'port': 8443})
    output = capsys.readouterr().out
    assert 'https://192.168.15.5:8443' in output
    assert 'open Windows Camera from the lesson' in output
    assert 'Optional live browser preview' in output
    output.encode('cp1252')
