"""Compare upstream Textual with this fork, one fresh interpreter per measurement.

Usage: python3 tools/benchmark.py [--python 3.12,3.14] [--runs 5]
Requires uv. Prints a Markdown table on stdout, progress and failures on stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tracemalloc
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple

UPSTREAM_VERSION = "8.2.8"
TIMEOUT_S = 600
SIDES = ("upstream", "fork")

_SCRIPT = Path(__file__).resolve()
_REPO_ROOT = _SCRIPT.parents[1]


class Workload(NamedTuple):
    """A measurement run in a worker process."""

    label: str
    unit: str
    traced: bool
    """Start tracemalloc before running."""
    repeat: bool
    """Take the median of `--runs` runs; otherwise run once."""
    run: Callable[[], Awaitable[float]]


_SIZE = (120, 40)


async def _demo_traced() -> float:
    import gc

    from textual.demo.demo_app import DemoApp

    async with DemoApp().run_test(size=_SIZE) as pilot:
        await pilot.pause()
        gc.collect()
        return tracemalloc.get_traced_memory()[0] / 1e6


async def _demo_rss() -> float:
    import resource

    from textual.demo.demo_app import DemoApp

    async with DemoApp().run_test(size=_SIZE) as pilot:
        await pilot.pause()
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return max_rss / (1e6 if sys.platform == "darwin" else 1e3)  # bytes vs KB


async def _churn() -> float:
    import gc

    from textual.app import App
    from textual.containers import Vertical
    from textual.widgets import Static

    async def cycle(container: Vertical) -> None:
        await container.mount_all(Static(str(i)) for i in range(1000))
        await pilot.pause()
        await container.remove_children()
        await pilot.pause()

    async with App().run_test(size=_SIZE) as pilot:
        container = Vertical()
        await pilot.app.mount(container)
        await cycle(container)
        gc.collect()
        baseline = tracemalloc.get_traced_memory()[0]
        for _ in range(20):
            await cycle(container)
        gc.collect()
        return (tracemalloc.get_traced_memory()[0] - baseline) / 1e6


async def _startup() -> float:
    from time import perf_counter

    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    class StartupApp(App):
        def compose(self) -> ComposeResult:
            with VerticalScroll():
                yield from (Static(str(i)) for i in range(200))

    start = perf_counter()
    async with StartupApp().run_test(size=_SIZE) as pilot:
        await pilot.pause()
        return (perf_counter() - start) * 1e3


async def _resize() -> float:
    from time import perf_counter

    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    class ResizeApp(App):
        def compose(self) -> ComposeResult:
            with VerticalScroll():
                yield from (Static(str(i)) for i in range(2000))

    async with ResizeApp().run_test(size=_SIZE) as pilot:
        await pilot.pause()
        start = perf_counter()
        await pilot.resize_terminal(160, 50)
        await pilot.pause()
        return (perf_counter() - start) * 1e3


async def _tree_clear() -> float:
    from time import perf_counter

    from textual.app import App, ComposeResult
    from textual.widgets import Tree

    class TreeApp(App):
        def compose(self) -> ComposeResult:
            yield Tree("root")

        def on_mount(self) -> None:
            root = self.query_one(Tree).root
            for i in range(10_000):
                root.add_leaf(f"leaf {i}")

    async with TreeApp().run_test(size=_SIZE) as pilot:
        await pilot.pause()
        start = perf_counter()
        pilot.app.query_one(Tree).root.remove_children()
        await pilot.pause()
        return (perf_counter() - start) * 1e3


async def _table_remove() -> float:
    from time import perf_counter

    from textual.app import App, ComposeResult
    from textual.widgets import DataTable

    class TableApp(App):
        def compose(self) -> ComposeResult:
            yield DataTable()

        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            table.add_columns("a", "b", "c")
            for i in range(10_000):
                table.add_row(i, i * 2, i * 3, key=str(i))

    async with TableApp().run_test(size=_SIZE) as pilot:
        await pilot.pause()
        table = pilot.app.query_one(DataTable)
        start = perf_counter()
        for i in range(10_000):
            table.remove_row(str(i))
        await pilot.pause()
        return (perf_counter() - start) * 1e3


WORKLOADS: dict[str, Workload] = {
    "demo_traced": Workload("Demo app, traced memory", "MB", True, False, _demo_traced),
    "demo_rss": Workload("Demo app, peak RSS", "MB", False, False, _demo_rss),
    "churn": Workload("Widget churn, retained memory", "MB", True, False, _churn),
    "startup": Workload("Startup to first frame", "ms", False, True, _startup),
    "resize": Workload("Resize, 2,000 widgets", "ms", False, True, _resize),
    "tree_clear": Workload("Tree, remove 10,000 nodes", "ms", False, True, _tree_clear),
    "table_remove": Workload(
        "DataTable, remove 10,000 rows", "ms", False, True, _table_remove
    ),
}


def parse_worker_output(stdout: str) -> float:
    """Return the number on the last non-empty line of a worker's stdout."""
    return float(stdout.strip().splitlines()[-1])


def measure(python: str, side: str, name: str, runs: int) -> float | None:
    """Return the median result of a workload, or None if any run fails."""
    source = (
        ["--with", f"textual=={UPSTREAM_VERSION}"]
        if side == "upstream"
        else ["--with-editable", str(_REPO_ROOT)]
    )
    command = [
        "uv", "run", "--isolated", "--no-project", "--python", python, *source,
        "python", str(_SCRIPT), "--worker", name,
    ]  # fmt: skip
    values = []
    warm_up = 1 if WORKLOADS[name].repeat else 0  # pays env setup and bytecode compile
    for _ in range(runs + warm_up if warm_up else 1):
        try:
            result = _run_worker(command, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            reason = f"timed out after {TIMEOUT_S} s"
        else:
            if result.returncode == 0:
                try:
                    values.append(parse_worker_output(result.stdout))
                    continue
                except (ValueError, IndexError):
                    reason = f"unparsable output {result.stdout!r}"
            else:
                reason = result.stderr.strip() or f"exit code {result.returncode}"
        print(f"{side} {python} {name}: {reason}", file=sys.stderr)
        return None
    return statistics.median(values[warm_up:])


def format_value(value: float | None, unit: str) -> str:
    """Format a measurement for the table."""
    return "n/a" if value is None else f"{value:.1f} {unit}"


def format_change(upstream: float | None, fork: float | None) -> str:
    """Format the fork's change relative to upstream as a signed percentage."""
    if upstream is None or fork is None or upstream == 0:
        return "n/a"
    return f"{(fork - upstream) / upstream:+.1%}"


def render_table(
    results: dict[tuple[str, str, str], float | None], pythons: list[str]
) -> str:
    """Render results keyed by (python, side, workload name) as a Markdown table."""
    header = ["Workload"]
    for python in pythons:
        header += [f"{python} upstream", f"{python} fork", f"{python} change"]
    lines = [
        "| " + " | ".join(header) + " |",
        "|---|" + "---:|" * (len(header) - 1),
    ]
    for name, workload in WORKLOADS.items():
        cells = [f"{workload.label} ({workload.unit})"]
        for python in pythons:
            upstream = results.get((python, "upstream", name))
            fork = results.get((python, "fork", name))
            cells += [
                format_value(upstream, workload.unit),
                format_value(fork, workload.unit),
                format_change(upstream, fork),
            ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark, or a single workload in worker mode."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", default="3.12,3.14")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--worker", choices=WORKLOADS)
    args = parser.parse_args(argv)

    if args.worker:
        workload = WORKLOADS[args.worker]
        if workload.traced:
            tracemalloc.start()
        print(asyncio.run(workload.run()))
        return 0

    if shutil.which("uv") is None:
        sys.exit("uv is required: https://docs.astral.sh/uv/")
    pythons = args.python.split(",")
    results = {}
    for python in pythons:
        for name in WORKLOADS:
            for side in SIDES:
                print(f"{python} {side} {name}", file=sys.stderr)
                results[python, side, name] = measure(python, side, name, args.runs)
    print(render_table(results, pythons))
    return 0


def _run_worker(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a command, killing its whole process group if it times out.

    Raises:
        subprocess.TimeoutExpired: If the command outlives `timeout` seconds.
    """
    # uv does not forward the kill to the Python worker it starts, so the
    # worker gets its own session and the whole group is killed.
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


if __name__ == "__main__":
    sys.exit(main())
