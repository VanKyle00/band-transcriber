"""Sanity checks on the stem configuration. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.config import DEFAULT_STEMS, STEMS


def test_default_stems_exist():
    assert all(s in STEMS for s in DEFAULT_STEMS)


def test_tab_stems_have_tuning():
    for spec in STEMS.values():
        if "tab" in spec.outputs:
            assert spec.tuning, f"{spec.name} declares tab output but has no tuning"


def test_drums_are_percussion_core():
    drums = STEMS["drums"]
    assert drums.transcriber == "drums"
    assert drums.clef == "percussion"
    assert not drums.experimental


def test_guitar_piano_flagged_experimental():
    assert STEMS["guitar"].experimental
    assert STEMS["piano"].experimental


def test_request_matches_user_spec():
    # The user asked for: drums sheet music; guitar+bass tabs + sheet music.
    assert "sheet" in STEMS["drums"].outputs
    for inst in ("guitar", "bass"):
        assert "tab" in STEMS[inst].outputs
        assert "sheet" in STEMS[inst].outputs


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
