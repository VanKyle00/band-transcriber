"""Dependency-light tests for the tab artifact wiring (heavy steps are mocked).
Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pipeline.pipeline as P
from pipeline import storage
from pipeline.config import STEMS


def test_storage_maps_alphatex_to_text():
    assert storage._mime(Path("guitar.alphatex")) == "text/plain"


def test_build_tab_bass_returns_ascii_and_alphatex(monkeypatch):
    monkeypatch.setattr(P.tab, "midi_to_tabs", lambda midi, tuning: ("ASCII", "ALPHATEX"))
    assert P._build_tab("bass", Path("x.mid"), STEMS["bass"]) == ("ASCII", "ALPHATEX", None)


def test_build_tab_guitar_without_openfret_uses_heuristic(monkeypatch):
    monkeypatch.setattr(P.opentab, "available", lambda: False)
    monkeypatch.setattr(P.tab, "midi_to_tabs", lambda midi, tuning: ("ASCII", "ALPHATEX"))
    assert P._build_tab("guitar", Path("x.mid"), STEMS["guitar"]) == ("ASCII", "ALPHATEX", None)


def test_process_stem_emits_tab_alphatex(tmp_path, monkeypatch):
    monkeypatch.setattr(P.storage, "upload_artifact", lambda p, j: f"url:{Path(p).name}")
    monkeypatch.setattr(P.notation, "midi_to_musicxml",
                        lambda midi, out, clef: (Path(out).write_text("x"), Path(out))[1])
    monkeypatch.setattr(P.notation, "musicxml_to_pdf",
                        lambda xml, out: (Path(out).write_bytes(b"%PDF"), Path(out))[1])
    monkeypatch.setattr(P, "_build_tab", lambda name, midi, spec: ("ASCII", "ALPHATEX", None))

    midi_src = tmp_path / "in.mid"
    midi_src.write_bytes(b"MThd")
    out = P.process_stem("bass", tmp_path / "bass.wav", tmp_path / "work", "job1",
                         precomputed_midi=midi_src)

    assert out["tab"] == "url:bass.tab.txt"
    assert out["tab_alphatex"] == "url:bass.alphatex"
    assert out["warnings"] == []
