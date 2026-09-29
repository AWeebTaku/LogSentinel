"""Detached job runner: `python -m logsentinel.api.runner <run_dir> -- <command...>`.

Runs the command with stdout/stderr in <run_dir>/log, forwards SIGTERM to it (so the API can ask a source to
stop gracefully) and always writes the exit code to <run_dir>/exit, even when the command fails or is killed.
"""
import signal
import subprocess
import sys
from pathlib import Path


def main() -> int:
    run_dir = Path(sys.argv[1])
    cmd = sys.argv[sys.argv.index("--") + 1:]
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "log", "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        signal.signal(signal.SIGTERM, lambda *_: proc.send_signal(signal.SIGTERM))
        code = proc.wait()
    (run_dir / "exit").write_text(f"{code}\n")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
