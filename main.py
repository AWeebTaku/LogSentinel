"""Build and start the local LogSentinel application stack."""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
KAFKA_SCRIPT = ROOT / "scripts" / "kafka.sh"


def python_executable() -> Path:
    venv_python = ROOT / ".venv" / "bin" / "python"
    return venv_python if venv_python.is_file() else Path(sys.executable)


def child_environment() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (src, env.get("PYTHONPATH", ""))))
    return env


def check_python_dependencies(python: Path) -> None:
    required = ("fastapi", "uvicorn", "confluent_kafka")
    check = "import importlib.util, sys; missing = [m for m in sys.argv[1:] if not importlib.util.find_spec(m)]; print(', '.join(missing)); sys.exit(bool(missing))"
    result = subprocess.run(
        [str(python), "-c", check, *required], capture_output=True, text=True, check=False
    )
    if result.returncode:
        missing = result.stdout.strip()
        raise RuntimeError(
            f"Missing Python dependencies: {missing}. Install them with "
            "`uv pip install -e '.[dev]'` (or `python -m pip install -e '.[dev]'`)."
        )


def build_ui() -> None:
    ui_dir = ROOT / "ui"
    if not (ui_dir / "node_modules").is_dir():
        subprocess.run(["npm", "ci"], cwd=ui_dir, check=True)
    subprocess.run(["npm", "run", "build"], cwd=ui_dir, check=True)


def kafka_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 9092), timeout=0.5):
            return True
    except OSError:
        return False


def start_kafka() -> bool:
    if kafka_reachable():
        print("Kafka already available on 127.0.0.1:9092")
        return False

    tools_dir = Path(os.environ.get("LOGSENTINEL_TOOLS", Path.home() / ".local/share/logsentinel"))
    kafka_start = tools_dir / "kafka" / "bin" / "kafka-server-start.sh"
    if not kafka_start.is_file():
        subprocess.run(["bash", str(KAFKA_SCRIPT), "setup"], cwd=ROOT, check=True)
    subprocess.run(["bash", str(KAFKA_SCRIPT), "start"], cwd=ROOT, check=True)

    for _ in range(60):
        if kafka_reachable():
            return True
        time.sleep(1)
    raise RuntimeError("Kafka did not become available at 127.0.0.1:9092")


def wait_for_api(api: subprocess.Popen, url: str) -> None:
    for _ in range(60):
        if api.poll() is not None:
            raise RuntimeError(f"API server exited with status {api.returncode}")
        try:
            with urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"API did not become ready at {url}")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the LogSentinel web application locally.")
    parser.add_argument("--port", type=int, default=8000, help="local API/UI port (default: 8000)")
    parser.add_argument("--no-build", action="store_true", help="use the existing ui/dist without rebuilding")
    parser.add_argument("--no-streaming", action="store_true", help="skip Kafka and the alert sink")
    args = parser.parse_args()

    python = python_executable()
    env = child_environment()
    sink = api = None
    kafka_started = False
    try:
        check_python_dependencies(python)
        if args.no_build:
            if not (ROOT / "ui" / "dist" / "index.html").is_file():
                raise RuntimeError("ui/dist is missing; run without --no-build to build the UI")
        else:
            build_ui()

        if not args.no_streaming:
            kafka_started = start_kafka()
            sink = subprocess.Popen(
                [str(python), "-m", "logsentinel.alerts.sink"], cwd=ROOT, env=env
            )

        url = f"http://127.0.0.1:{args.port}"
        api = subprocess.Popen(
            [str(python), "-m", "uvicorn", "logsentinel.api.app:app", "--host", "127.0.0.1",
             "--port", str(args.port)],
            cwd=ROOT,
            env=env,
        )
        wait_for_api(api, url)
        print(f"LogSentinel is ready at {url} (API docs: {url}/docs). Press Ctrl+C to stop.", flush=True)

        while api.poll() is None:
            if sink is not None and sink.poll() is not None:
                raise RuntimeError(f"Alert sink exited with status {sink.returncode}")
            time.sleep(0.5)
        return api.returncode or 0
    except KeyboardInterrupt:
        return 130
    finally:
        stop_process(api)
        stop_process(sink)
        if kafka_started:
            subprocess.run(["bash", str(KAFKA_SCRIPT), "stop"], cwd=ROOT, check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"LogSentinel startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc