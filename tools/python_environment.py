"""Use the project's Python environment for installation and tray launch."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent


def selected_python(root=ROOT, windowed=False):
    name = "pythonw.exe" if windowed else "python.exe"
    environment = root / ".venv"
    if environment.exists():
        executable = environment / "Scripts" / name
        if not executable.is_file():
            raise RuntimeError("Project .venv is incomplete; repair it before starting the bot")
        return executable
    # Legacy global installations remain usable. Once installed with our setup
    # script, both launchers select .venv regardless of PATH or launcher defaults.
    executable = Path(sys.executable)
    if windowed and executable.name.lower() == "python.exe":
        candidate = executable.with_name("pythonw.exe")
        if candidate.is_file():
            return candidate
    return executable


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--launch", action="store_true")
    parser.add_argument("port", nargs="?", type=int)
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required")
    if args.install:
        if not (ROOT / ".venv").exists():
            venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
        executable = selected_python(ROOT)
        subprocess.run([str(executable), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
                       cwd=ROOT, check=True)
        print(f"Installed project environment: {executable}")
    else:
        command = [str(selected_python(ROOT, windowed=True)), str(ROOT / "tray_runner.py")]
        if args.port is not None:
            command.append(str(args.port))
        subprocess.Popen(command, cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


if __name__ == "__main__":
    main()
