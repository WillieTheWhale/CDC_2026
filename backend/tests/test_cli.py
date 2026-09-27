# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""The `trace` CLI: every stage parses, the pipeline covers every downstream artefact, refresh goes where it belongs."""
import inspect
import importlib

import pytest

from trace_backend import cli


def test_help_builds_without_conflicting_subcommands(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for stage in cli.STAGES:
        assert stage in out


def test_pipeline_order_ends_with_downstream_map_layers():
    assert list(cli.STAGES) == ["prepare", "edges", "models", "risk", "export", "us-routes", "flows"]


def test_refresh_only_passed_to_stages_that_accept_it():
    for name, (mod, fn, _) in cli.STAGES.items():
        params = inspect.signature(getattr(importlib.import_module(mod), fn)).parameters
        assert ("refresh" in params) == (name in cli.REFRESH_STAGES), name
