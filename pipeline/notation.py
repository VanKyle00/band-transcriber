"""MIDI -> MusicXML -> engraved PDF (music21 + LilyPond).

MusicXML is the interchange format the browser score viewer (OSMD) reads; the PDF is
the downloadable engraved score. LilyPond is invoked headlessly via music21, so no
X11 is required in the container.
"""
from __future__ import annotations

from pathlib import Path

_CLEFS = {
    "treble": "TrebleClef",
    "bass": "BassClef",
    "treble_8vb": "Treble8vbClef",
    "bass_8vb": "Bass8vbClef",
    "percussion": "PercussionClef",
}


def configure_lilypond(path: str | None = None) -> None:
    """Point music21 at the LilyPond binary (call once at startup if needed)."""
    from music21 import environment

    if path:
        environment.set("lilypondPath", path)


def _apply_clef(score, clef_name: str) -> None:
    from music21 import clef as m21clef

    cls = _CLEFS.get(clef_name)
    if not cls:  # e.g. "grand" — leave music21's default staff handling
        return
    for part in score.parts:
        part.insert(0, getattr(m21clef, cls)())
        break


def _apply_key(score) -> None:
    """Insert a detected key signature on every part (readability only; pitches unchanged)."""
    from music21 import key as m21key

    try:
        analyzed = score.analyze("key")
    except Exception:
        return
    if analyzed is None:
        return
    for part in score.parts:
        part.insert(0, m21key.KeySignature(analyzed.sharps))


def midi_to_musicxml(midi_path: Path, out_xml: Path, clef_name: str = "treble") -> Path:
    from music21 import converter

    score = converter.parse(str(midi_path))
    _apply_clef(score, clef_name)
    _apply_key(score)
    out_xml.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(out_xml))
    return out_xml


def musicxml_to_pdf(xml_path: Path, out_pdf: Path) -> Path:
    """Engrave a MusicXML file to PDF via LilyPond. Raises on failure."""
    from music21 import converter

    score = converter.parse(str(xml_path))
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    written = score.write("lilypond.pdf", fp=str(out_pdf.with_suffix("")))
    produced = Path(written)
    if produced != out_pdf:
        produced.replace(out_pdf)
    return out_pdf
