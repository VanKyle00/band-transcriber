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


def _depercuss(midi_path: Path) -> Path:
    """Rewrite a drum MIDI as a *pitched* MIDI for engraving only.

    music21's LilyPond exporter crashes on multi-measure percussion (Unpitched) parts
    (lily/translate.py: ``self.context.contents`` is None). Pitched parts engrave fine,
    so for the score we drop the drum flag — GM percussion pitches then land on the
    staff. The uploaded MIDI artifact keeps its real percussion track.
    """
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    for inst in pm.instruments:
        inst.is_drum = False
    out = midi_path.with_name(midi_path.stem + ".pitched.mid")
    pm.write(str(out))
    return out


def midi_to_musicxml(midi_path: Path, out_xml: Path, clef_name: str = "treble") -> Path:
    from music21 import converter

    src = _depercuss(midi_path) if clef_name == "percussion" else midi_path
    score = converter.parse(str(src))
    _apply_clef(score, clef_name)
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
