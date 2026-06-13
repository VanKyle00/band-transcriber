"""Tests for the open-fret gating logic. Run: python -m pytest pipeline/tests"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import opentab


def _set(key: str, value: str | None) -> str | None:
    old = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    return old


def test_unavailable_when_paths_missing():
    repo, model = _set("OPENFRET_REPO_DIR", "/no/such/repo"), _set("OPENFRET_MODEL_DIR", "/no/such/model")
    try:
        assert opentab.available() is False
    finally:
        _set("OPENFRET_REPO_DIR", repo)
        _set("OPENFRET_MODEL_DIR", model)


def test_available_when_repo_and_weights_present():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts" / "inference.py").write_text("x", encoding="utf-8")
        model = Path(d) / "model"
        model.mkdir()
        old_repo, old_model = _set("OPENFRET_REPO_DIR", str(repo)), _set("OPENFRET_MODEL_DIR", str(model))
        try:
            assert opentab.available() is True
        finally:
            _set("OPENFRET_REPO_DIR", old_repo)
            _set("OPENFRET_MODEL_DIR", old_model)


def test_inference_raises_when_unavailable():
    repo, model = _set("OPENFRET_REPO_DIR", "/no/such/repo"), _set("OPENFRET_MODEL_DIR", "/no/such/model")
    try:
        raised = False
        try:
            opentab.midi_to_tab_openfret("nope.mid")
        except RuntimeError:
            raised = True
        assert raised, "should raise (so caller falls back) when open-fret is unavailable"
    finally:
        _set("OPENFRET_REPO_DIR", repo)
        _set("OPENFRET_MODEL_DIR", model)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
