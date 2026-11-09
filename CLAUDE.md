# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Poetry is the canonical toolchain (Makefile and CI use it; `uv.lock` also exists but is not used by CI).

```bash
make setup                      # poetry install + --extras syntax (tree-sitter, Python >= 3.10 only)
make test                       # pytest tests/ -n 16 --dist=loadgroup
poetry run pytest tests/test_strip.py::test_name      # single test
poetry run pytest tests/snapshot_tests/test_snapshots.py -k name -vv
poetry run pytest tests -m 'not syntax'               # skip tree-sitter tests (as CI does on 3.9)
make test-snapshot-update       # regenerate snapshot SVGs after verifying the diff is correct
make typecheck                  # mypy src/textual
make format                     # black src (pre-commit also runs isort --profile black, pycln, absolufy-imports)
make docs-serve-offline         # preview docs locally
python -m textual               # demo app
```

pytest runs with `asyncio_mode = "auto"`, so `async def test_...` needs no marker. Code must stay compatible with Python 3.9 (`from __future__ import annotations` is used throughout).

## Architecture

Class hierarchy: `MessagePump` (`message_pump.py`, async message queue + handler dispatch via `on_<message>` / `@on`) → `DOMNode` (`dom.py`, tree, CSS classes/ids, styles, reactive attributes) → `Widget` (`widget.py`) → `Screen` (`screen.py`). `App` (`app.py`) is also a `DOMNode` and owns the screen stack, modes, themes, bindings and the `Driver`.

Rendering pipeline:
- A widget produces content via `render()` (returning a `Visual`/`Content`/Rich renderable, see `visual.py`, `content.py`) or `render_line(y)` for line-API widgets (e.g. `scroll_view.py`, `widgets/_data_table.py`).
- Output is a list of `Strip` (`strip.py`): an immutable line of Rich `Segment`s with cached crop/style operations.
- `_styles_cache.py` applies borders, padding, tint and background around the content strips.
- `Compositor` (`_compositor.py`) arranges widgets per screen (via `_arrange.py` and `layouts/`), maps regions to widgets, and renders only changed regions as `CompositorUpdate`s (`LayoutUpdate`, `ChopsUpdate`, `InlineUpdate`).
- A `Driver` (`drivers/`: linux, windows, inline, headless, web) writes the result to the terminal and parses input (`_xterm_parser.py`, `_keyboard_protocol.py`) into events.

CSS (`css/`): `tokenizer.py`/`tokenize.py` → `parse.py` → `stylesheet.py` (rule matching, `match.py`) → `styles.py` (`Styles`/`RenderStyles`, properties defined as descriptors in `_style_properties.py`, validation in `_styles_builder.py`). Widgets declare `DEFAULT_CSS`; apps use `CSS`/`CSS_PATH`. `design.py` + `theme.py` generate the theme CSS variables.

Other cross-cutting pieces: `reactive.py` (reactive/var descriptors with `watch_`/`validate_`/`compute_` methods), `binding.py` + `actions.py` (key bindings → `action_*` methods), `worker.py`/`worker_manager.py` (`@work` background tasks), `pilot.py` (`App.run_test()` driver for tests), `widgets/` (public widgets re-exported lazily from `widgets/__init__.py`). Modules prefixed with `_` are private.

## Testing

- Tests drive apps headlessly with `async with app.run_test() as pilot:`.
- Visual changes need snapshot tests in `tests/snapshot_tests/test_snapshots.py` using the `snap_compare` fixture (apps live in `snapshot_apps/` or `docs/examples/`). Never hand-edit `tests/snapshot_tests/__snapshots__/`; inspect `snapshot_report.html` on failure, then run `make test-snapshot-update`.
- Bug fixes should include a regression test referencing the issue.

## Contribution conventions

- Update `CHANGELOG.md` (Keep a Changelog format, entries link to the PR) under the unreleased section.
- All public code has docstrings in the existing Google style (rendered by mkdocstrings).
- Upstream PRs must link to an issue/discussion approved by a maintainer; AI-generated PRs must say so and name the agent (`AI_POLICY.md`).
