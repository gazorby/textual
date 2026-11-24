from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import time
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def benchmark() -> ModuleType:
    """Load tools/benchmark.py as a module."""
    path = Path(__file__).parents[1] / "tools" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_worker_output_takes_last_line(benchmark: ModuleType) -> None:
    """Test that stray lines before the result are ignored."""
    assert benchmark.parse_worker_output("noise\n12.5\n\n") == 12.5


def test_format_change(benchmark: ModuleType) -> None:
    """Test that the change is a signed percentage, or n/a without a usable baseline."""
    assert benchmark.format_change(200.0, 50.0) == "-75.0%"
    assert benchmark.format_change(100.0, 110.0) == "+10.0%"
    assert benchmark.format_change(None, 1.0) == "n/a"
    assert benchmark.format_change(0.0, 1.0) == "n/a"


def test_render_table_shows_na(
    benchmark: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a failed measurement renders as n/a in its value and change cells."""
    monkeypatch.setattr(
        benchmark,
        "WORKLOADS",
        {"x": benchmark.Workload("Thing", "ms", False, True, None)},
    )
    results = {("3.14", "upstream", "x"): 10.0, ("3.14", "fork", "x"): None}
    assert benchmark.render_table(results, ["3.14"]) == (
        "| Workload | 3.14 upstream | 3.14 fork | 3.14 change |\n"
        "|---|---:|---:|---:|\n"
        "| Thing (ms) | 10.0 ms | n/a | n/a |"
    )


def test_measure_returns_none_on_timeout(
    benchmark: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a worker timing out yields None instead of hanging or raising."""

    def fake_run(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="uv", timeout=1)

    monkeypatch.setattr(benchmark, "_run_worker", fake_run)
    assert benchmark.measure("3.14", "upstream", "startup", 1) is None


def test_main_requires_uv(
    benchmark: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the benchmark exits at once when uv is missing."""
    monkeypatch.setattr(benchmark.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="uv is required"):
        benchmark.main([])


def test_unknown_worker_rejected(benchmark: ModuleType) -> None:
    """Test that an unknown workload name is rejected by argparse."""
    with pytest.raises(SystemExit) as error:
        benchmark.main(["--worker", "nope"])
    assert error.value.code == 2


def test_measure_ignores_discovered_environments(
    benchmark: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that workers run isolated, so the repo's .venv cannot replace upstream."""
    commands = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="1.0\n", stderr="")

    monkeypatch.setattr(benchmark, "_run_worker", fake_run)
    benchmark.measure("3.14", "upstream", "demo_rss", 1)
    assert commands[0][:3] == ["uv", "run", "--isolated"]


def test_format_change_keeps_near_total_drops_distinct(benchmark: ModuleType) -> None:
    """Test that a 99.5% drop is not rounded to -100%, which would read as zero."""
    assert benchmark.format_change(1000.0, 5.0) == "-99.5%"


def test_measure_discards_warm_up_run(
    benchmark: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a timed workload's first run, paying one-off costs, is left out."""
    outputs = iter(["1000.0", "1.0", "2.0", "3.0"])

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(command, 0, stdout=next(outputs), stderr="")

    monkeypatch.setattr(benchmark, "_run_worker", fake_run)
    assert benchmark.measure("3.14", "fork", "startup", 2) == 1.5


def test_run_worker_kills_grandchildren_on_timeout(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    """Test that a timeout kills the whole process group, not only uv."""
    pid_file = tmp_path / "pid"
    with pytest.raises(subprocess.TimeoutExpired):
        benchmark._run_worker(
            ["sh", "-c", f"sleep 30 & echo $! > {pid_file}; wait"], timeout=1
        )
    grandchild = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(grandchild, signal.SIGKILL)
    pytest.fail("grandchild outlived the timeout")
