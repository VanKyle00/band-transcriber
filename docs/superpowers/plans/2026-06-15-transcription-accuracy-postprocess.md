# Transcription Accuracy Post-Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert a cheap, CPU-only post-processing layer between transcription and notation — detect the song's real tempo once, quantize each stem's notes to a beat grid, clean up spurious/overlapping notes, and add a key signature — so transcriptions read accurately instead of being rendered against a hardcoded 120 BPM.

**Architecture:** A new `pipeline/postprocess.py` with a pure-logic core (`quantize_and_clean`, `_fold_tempo` — no ML deps, unit-testable anywhere) plus two thin I/O adapters that import their heavy deps lazily (`detect_tempo` via librosa, `apply_to_midi` via pretty_midi). Tempo is detected once on the full mix in the orchestrators (`run_pipeline`, `process_job`) and threaded into each stem's `process_stem`. Melodic stems get `apply_to_midi`; drums get the real BPM passed into `drumnotation`; notation gains a detected key signature.

**Tech Stack:** Python 3.11, librosa (beat tracking), pretty_midi (MIDI I/O), music21 (key analysis), pytest. Modal for orchestration.

---

## File Structure

- `pipeline/postprocess.py` — **NEW.** The whole post-processing layer: `Note`/`Grid` types, `_fold_tempo`, `quantize_and_clean` (+ `_merge_same_pitch`, `_enforce_monophony`), `detect_tempo`, `apply_to_midi`.
- `pipeline/tests/test_postprocess.py` — **NEW.** Dependency-light tests for the pure core; `importorskip`-guarded tests for the pretty_midi adapter.
- `pipeline/drumnotation.py` — **MODIFY.** `_slots` / `render_drum_musicxml` / `render_drum_pdf` accept a `bpm` argument (default 120 = unchanged behavior).
- `pipeline/notation.py` — **MODIFY.** `midi_to_musicxml` inserts a detected key signature via a new `_apply_key`.
- `pipeline/pipeline.py` — **MODIFY.** `run_pipeline` detects tempo; `process_stem` gains a `grid` param, calls `apply_to_midi` for melodic stems and passes `bpm` to drum notation.
- `modal_app.py` — **MODIFY.** `process_job` detects tempo and threads a `(bpm, beat_offset)` tuple into `transcribe_stem`, which reconstructs a `Grid` and forwards it to `process_stem`.

All work happens on the existing feature branch `transcription-accuracy-postprocess`.

---

## Task 1: Post-processing module skeleton + tempo fold

**Files:**
- Create: `pipeline/postprocess.py`
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_postprocess.py`:

```python
"""Tests for the (dependency-light) post-processing core. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.postprocess import Grid, Note, _fold_tempo


def test_fold_tempo_in_range_unchanged():
    assert _fold_tempo(120.0) == 120.0


def test_fold_tempo_doubles_slow():
    assert _fold_tempo(50.0) == 100.0


def test_fold_tempo_halves_fast():
    assert _fold_tempo(200.0) == 100.0


def test_fold_tempo_rejects_nonpositive():
    with pytest.raises(ValueError):
        _fold_tempo(0.0)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok  {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name}: {exc}")
    print("done")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.postprocess'`

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/postprocess.py`:

```python
"""Post-processing layer: tempo detection + rhythmic quantization + note cleanup.

Sits between transcription (raw MIDI) and notation. The pure-logic core
(`quantize_and_clean`, `_fold_tempo`) imports no ML deps so it unit-tests anywhere;
`detect_tempo` (librosa) and `apply_to_midi` (pretty_midi) import their heavy deps lazily.
"""
from __future__ import annotations

import math
from typing import NamedTuple


class Note(NamedTuple):
    start: float
    end: float
    pitch: int
    velocity: int


class Grid(NamedTuple):
    bpm: float
    beat_offset: float


def _fold_tempo(bpm: float) -> float:
    """Fold a detected tempo into a musical 60-180 BPM range (half/double-time guard)."""
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError(f"bad tempo: {bpm}")
    while bpm < 60:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return bpm
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/postprocess.py pipeline/tests/test_postprocess.py
git commit -m "feat(postprocess): Note/Grid types + tempo fold guard"
```

---

## Task 2: Grid quantization + spurious-note removal

**Files:**
- Modify: `pipeline/postprocess.py`
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Append these imports and tests to `pipeline/tests/test_postprocess.py` (add `quantize_and_clean` to the existing `from pipeline.postprocess import ...` line so it reads `from pipeline.postprocess import Grid, Note, _fold_tempo, quantize_and_clean`):

```python
def test_quantize_snaps_to_16th_grid():
    grid = Grid(bpm=120.0, beat_offset=0.0)        # slot = (60/120)/4 = 0.125s
    out = quantize_and_clean([Note(0.13, 0.60, 60, 100)], grid, monophonic=False)
    assert out == [Note(0.125, 0.625, 60, 100)]


def test_quantize_drops_spurious_short_notes():
    grid = Grid(bpm=120.0, beat_offset=0.0)        # half-slot = 0.0625s
    notes = [Note(0.0, 0.04, 60, 100),             # 0.04 < 0.0625 -> dropped
             Note(0.0, 0.25, 62, 100)]             # kept
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert [n.pitch for n in out] == [62]


def test_quantize_enforces_minimum_one_slot():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    # 0.46..0.54 both snap to 0.5 -> must be widened to one slot (0.5..0.625)
    out = quantize_and_clean([Note(0.46, 0.54, 60, 100)], grid, monophonic=False)
    assert out == [Note(0.5, 0.625, 60, 100)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: FAIL — `ImportError: cannot import name 'quantize_and_clean'`

- [ ] **Step 3: Write minimal implementation**

Append to `pipeline/postprocess.py`:

```python
def _slot_seconds(grid: Grid, subdiv: int) -> float:
    return (60.0 / grid.bpm) / subdiv


def _snap(t: float, grid: Grid, slot: float) -> float:
    return grid.beat_offset + round((t - grid.beat_offset) / slot) * slot


def quantize_and_clean(notes, grid: Grid, *, monophonic: bool, subdiv: int = 4) -> list[Note]:
    """Snap notes to a 16th grid and drop spurious ones.

    (Same-pitch merge + monophony resolution are layered in by Task 3.)
    """
    slot = _slot_seconds(grid, subdiv)
    kept = [Note(*n) for n in notes if (n[1] - n[0]) >= slot / 2]
    snapped: list[Note] = []
    for n in kept:
        s = _snap(n.start, grid, slot)
        e = _snap(n.end, grid, slot)
        if e < s + slot:
            e = s + slot
        snapped.append(n._replace(start=s, end=e))
    snapped.sort(key=lambda n: (n.start, n.pitch))
    return snapped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/postprocess.py pipeline/tests/test_postprocess.py
git commit -m "feat(postprocess): grid quantization + spurious-note removal"
```

---

## Task 3: Same-pitch merge + monophony enforcement

**Files:**
- Modify: `pipeline/postprocess.py`
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_postprocess.py`:

```python
def test_merge_consecutive_same_pitch_keeps_max_velocity():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 60, 90), Note(0.125, 0.25, 60, 110)]
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert out == [Note(0.0, 0.25, 60, 110)]


def test_does_not_merge_distant_same_pitch():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 60, 100), Note(0.5, 0.625, 60, 100)]
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert len(out) == 2


def test_polyphonic_keeps_overlapping_pitches():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    chord = [Note(0.0, 0.5, 60, 100), Note(0.0, 0.5, 64, 100)]
    out = quantize_and_clean(chord, grid, monophonic=False)
    assert len(out) == 2


def test_monophony_drops_overlap_keeps_longer():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 60, 100), Note(0.0, 0.5, 67, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert [n.pitch for n in out] == [67]


def test_monophony_truncates_lingering_note():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    # 60 lingers (snaps 0.0..0.375) into 62 (snaps 0.25..0.5) -> 60 truncated to 0.25
    notes = [Note(0.0, 0.36, 60, 100), Note(0.25, 0.5, 62, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert out == [Note(0.0, 0.25, 60, 100), Note(0.25, 0.5, 62, 100)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: FAIL — the new merge + monophony tests fail (e.g. `test_merge_consecutive_same_pitch_keeps_max_velocity` returns 2 notes, `test_monophony_drops_overlap_keeps_longer` returns both pitches), because those behaviors aren't implemented yet. The polyphonic test already passes.

- [ ] **Step 3: Write minimal implementation**

Add the two helpers to `pipeline/postprocess.py` (above `quantize_and_clean`):

```python
def _merge_same_pitch(notes: list[Note], slot: float) -> list[Note]:
    """Merge consecutive same-pitch notes separated by less than one slot."""
    result: list[Note] = []
    last_idx: dict[int, int] = {}
    for n in notes:
        i = last_idx.get(n.pitch)
        if i is not None and n.start - result[i].end < slot:
            p = result[i]
            result[i] = p._replace(end=max(p.end, n.end),
                                   velocity=max(p.velocity, n.velocity))
        else:
            last_idx[n.pitch] = len(result)
            result.append(n)
    return result


def _enforce_monophony(notes: list[Note], slot: float) -> list[Note]:
    """Resolve overlaps so at most one note sounds at a time (monophonic stems)."""
    notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    result: list[Note] = []
    for n in notes:
        if result and n.start < result[-1].end:
            prev = result[-1]
            if n.start - prev.start >= slot / 2:
                result[-1] = prev._replace(end=n.start)   # truncate prev, keep both
                result.append(n)
            elif (n.end - n.start) > (prev.end - prev.start):
                result[-1] = n                             # prev too short -> n wins
            # else: drop n (prev wins)
        else:
            result.append(n)
    return result
```

Then change the last two lines of `quantize_and_clean` from:

```python
    snapped.sort(key=lambda n: (n.start, n.pitch))
    return snapped
```

to:

```python
    snapped.sort(key=lambda n: (n.start, n.pitch))
    merged = _merge_same_pitch(snapped, slot)
    if monophonic:
        merged = _enforce_monophony(merged, slot)
    return merged
```

Also update the `quantize_and_clean` docstring to drop the "(Same-pitch merge ... Task 3)" note since it's now implemented.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/postprocess.py pipeline/tests/test_postprocess.py
git commit -m "feat(postprocess): same-pitch merge + monophony enforcement"
```

---

## Task 4: `detect_tempo` + `apply_to_midi` I/O adapters

**Files:**
- Modify: `pipeline/postprocess.py`
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_postprocess.py`:

```python
def test_apply_to_midi_quantizes_and_sets_tempo(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    from pipeline.postprocess import apply_to_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0.13, end=0.60))
    pm.instruments.append(inst)
    midi = tmp_path / "t.mid"
    pm.write(str(midi))

    apply_to_midi(midi, Grid(bpm=120.0, beat_offset=0.0), monophonic=False)

    out = pretty_midi.PrettyMIDI(str(midi))
    note = out.instruments[0].notes[0]
    assert abs(note.start - 0.125) < 1e-3
    assert abs(note.end - 0.625) < 1e-3
    _, tempi = out.get_tempo_changes()
    assert abs(float(tempi[0]) - 120.0) < 1e-2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_postprocess.py::test_apply_to_midi_quantizes_and_sets_tempo -v`
Expected: FAIL — `ImportError: cannot import name 'apply_to_midi'` (or SKIP if pretty_midi is not installed in this env — that is acceptable; the integration step covers it).

- [ ] **Step 3: Write minimal implementation**

Append to `pipeline/postprocess.py`:

```python
def detect_tempo(wav) -> Grid:
    """Estimate a global tempo + first-beat offset from the mix (librosa beat tracking)."""
    import librosa

    y, sr = librosa.load(str(wav), mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = _fold_tempo(float(tempo))
    beat_offset = float(beats[0]) if len(beats) else 0.0
    return Grid(bpm=bpm, beat_offset=beat_offset)


def apply_to_midi(midi_path, grid: Grid, *, monophonic: bool, subdiv: int = 4):
    """Quantize+clean every instrument in a MIDI file and rewrite it at the grid tempo."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    out = pretty_midi.PrettyMIDI(initial_tempo=float(grid.bpm))
    for inst in pm.instruments:
        raw = [Note(n.start, n.end, n.pitch, n.velocity) for n in inst.notes]
        cleaned = quantize_and_clean(raw, grid, monophonic=monophonic, subdiv=subdiv)
        new_inst = pretty_midi.Instrument(program=inst.program, is_drum=inst.is_drum,
                                          name=inst.name)
        new_inst.notes = [pretty_midi.Note(velocity=int(c.velocity), pitch=int(c.pitch),
                                           start=float(c.start), end=float(c.end))
                          for c in cleaned]
        out.instruments.append(new_inst)
    out.write(str(midi_path))
    return midi_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: PASS (14 passed) — or 13 passed + 1 skipped if pretty_midi is unavailable locally.

- [ ] **Step 5: Commit**

```bash
git add pipeline/postprocess.py pipeline/tests/test_postprocess.py
git commit -m "feat(postprocess): detect_tempo + apply_to_midi adapters"
```

---

## Task 5: Thread real tempo into drum notation

**Files:**
- Modify: `pipeline/drumnotation.py` (`_slots`, `render_drum_musicxml`, `render_drum_pdf`)
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_postprocess.py`:

```python
def test_drum_slots_scale_with_tempo(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    from pipeline.drumnotation import _slots

    pm = pretty_midi.PrettyMIDI()
    drum = pretty_midi.Instrument(program=0, is_drum=True)
    drum.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.0, end=0.05))
    drum.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=1.0, end=1.05))
    pm.instruments.append(drum)
    midi = tmp_path / "d.mid"
    pm.write(str(midi))

    slow = _slots(midi, bpm=60.0)    # 16th = 0.25s -> hit at 1.0s lands in slot 4
    fast = _slots(midi, bpm=120.0)   # 16th = 0.125s -> hit at 1.0s lands in slot 8
    slow_hits = [i for i, s in enumerate(slow) if 36 in s]
    fast_hits = [i for i, s in enumerate(fast) if 36 in s]
    assert fast_hits[1] > slow_hits[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_postprocess.py::test_drum_slots_scale_with_tempo -v`
Expected: FAIL — `TypeError: _slots() got an unexpected keyword argument 'bpm'` (or SKIP if pretty_midi unavailable).

- [ ] **Step 3: Write minimal implementation**

In `pipeline/drumnotation.py`, change `_slots` to accept `bpm` (default keeps current behavior). Replace:

```python
def _slots(midi_path: Path) -> list[set[int]]:
    """Quantize the drum MIDI onto a 16th-note grid; each slot holds the GM pitches hit there."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    sec_per_slot = (60.0 / _ASSUMED_BPM) * (4.0 / _GRID)
```

with:

```python
def _slots(midi_path: Path, bpm: float = _ASSUMED_BPM) -> list[set[int]]:
    """Quantize the drum MIDI onto a 16th-note grid; each slot holds the GM pitches hit there."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    sec_per_slot = (60.0 / bpm) * (4.0 / _GRID)
```

Then thread `bpm` through the two public renderers. Replace the `render_drum_musicxml` signature line and its `_slots(...)` call:

```python
def render_drum_musicxml(midi_path: Path, out_xml: Path) -> Path:
    """Emit a percussion-staff MusicXML (kick/snare/hi-hat at standard positions, x hi-hats)."""
    slots = _slots(midi_path)
```

with:

```python
def render_drum_musicxml(midi_path: Path, out_xml: Path, bpm: float = _ASSUMED_BPM) -> Path:
    """Emit a percussion-staff MusicXML (kick/snare/hi-hat at standard positions, x hi-hats)."""
    slots = _slots(midi_path, bpm)
```

And replace the `render_drum_pdf` signature line and its `_slots(...)` call:

```python
def render_drum_pdf(midi_path: Path, out_pdf: Path) -> Path:
    """Engrave a clean printable drum chart via LilyPond's drum mode."""
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    work = out_pdf.parent
    ly = work / "drums.ly"
    ly.write_text(_lilypond(_slots(midi_path)), encoding="utf-8")
```

with:

```python
def render_drum_pdf(midi_path: Path, out_pdf: Path, bpm: float = _ASSUMED_BPM) -> Path:
    """Engrave a clean printable drum chart via LilyPond's drum mode."""
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    work = out_pdf.parent
    ly = work / "drums.ly"
    ly.write_text(_lilypond(_slots(midi_path, bpm)), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: PASS (15 passed, or fewer-with-skips if pretty_midi unavailable).

- [ ] **Step 5: Commit**

```bash
git add pipeline/drumnotation.py pipeline/tests/test_postprocess.py
git commit -m "feat(drumnotation): accept real bpm instead of fixed 120"
```

---

## Task 6: Key signature in notation

**Files:**
- Modify: `pipeline/notation.py` (`midi_to_musicxml`, new `_apply_key`)
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_postprocess.py`:

```python
def test_apply_key_inserts_key_signature():
    pytest.importorskip("music21")
    from music21 import key as m21key
    from music21 import note as m21note
    from music21 import stream

    from pipeline.notation import _apply_key

    score = stream.Score()
    part = stream.Part()
    for p in ("C4", "E4", "G4", "C5"):
        part.append(m21note.Note(p, quarterLength=1))
    score.append(part)

    _apply_key(score)

    found = score.parts[0].getElementsByClass(m21key.KeySignature)
    assert len(found) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_postprocess.py::test_apply_key_inserts_key_signature -v`
Expected: FAIL — `ImportError: cannot import name '_apply_key'` (or SKIP if music21 unavailable).

- [ ] **Step 3: Write minimal implementation**

In `pipeline/notation.py`, add `_apply_key` (place it after `_apply_clef`):

```python
def _apply_key(score) -> None:
    """Insert a detected key signature on every part (readability only; pitches unchanged)."""
    from music21 import key as m21key

    try:
        analyzed = score.analyze("key")
    except Exception:
        return
    for part in score.parts:
        part.insert(0, m21key.KeySignature(analyzed.sharps))
```

Then call it in `midi_to_musicxml`. Replace:

```python
def midi_to_musicxml(midi_path: Path, out_xml: Path, clef_name: str = "treble") -> Path:
    from music21 import converter

    score = converter.parse(str(midi_path))
    _apply_clef(score, clef_name)
    out_xml.parent.mkdir(parents=True, exist_ok=True)
```

with:

```python
def midi_to_musicxml(midi_path: Path, out_xml: Path, clef_name: str = "treble") -> Path:
    from music21 import converter

    score = converter.parse(str(midi_path))
    _apply_clef(score, clef_name)
    _apply_key(score)
    out_xml.parent.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_postprocess.py -v`
Expected: PASS (16 passed, or fewer-with-skips if music21 unavailable).

- [ ] **Step 5: Commit**

```bash
git add pipeline/notation.py pipeline/tests/test_postprocess.py
git commit -m "feat(notation): insert detected key signature for readable spelling"
```

---

## Task 7: Wire post-processing into the local pipeline

**Files:**
- Modify: `pipeline/pipeline.py` (`run_pipeline`, `process_stem`, imports)

> No new unit test: `process_stem` calls `storage.upload_artifact` (needs Supabase) and transcription (needs ML deps), so it is verified by the import check below + the existing suite staying green + the integration step in Task 9. The post-processing logic itself is already covered by Tasks 1–6.

- [ ] **Step 1: Add the import**

In `pipeline/pipeline.py`, change:

```python
from . import download, drumnotation, notation, opentab, separate, storage, tab
```

to:

```python
from . import download, drumnotation, notation, opentab, postprocess, separate, storage, tab
```

- [ ] **Step 2: Add the `grid` parameter to `process_stem`**

Change the signature:

```python
def process_stem(stem_name: str, stem_wav: Path, workdir: Path, job_id: str,
                 precomputed_midi: Path | None = None) -> dict:
```

to:

```python
def process_stem(stem_name: str, stem_wav: Path, workdir: Path, job_id: str,
                 precomputed_midi: Path | None = None, grid=None) -> dict:
```

- [ ] **Step 3: Quantize melodic MIDI before upload**

In `process_stem`, replace:

```python
    out["midi"] = storage.upload_artifact(midi, job_id)
```

with:

```python
    if grid is not None and spec.transcriber == "melodic":
        try:
            postprocess.apply_to_midi(midi, grid, monophonic=not spec.polyphonic)
        except Exception as exc:
            out["warnings"].append(f"post-processing failed: {exc}")
    out["midi"] = storage.upload_artifact(midi, job_id)
```

- [ ] **Step 4: Pass the real bpm to drum notation**

In `process_stem`, replace:

```python
        try:
            xml = drumnotation.render_drum_musicxml(midi, sdir / f"{stem_name}.musicxml")
            out["musicxml"] = storage.upload_artifact(xml, job_id)
            pdf = drumnotation.render_drum_pdf(midi, sdir / f"{stem_name}.pdf")
            out["sheet_pdf"] = storage.upload_artifact(pdf, job_id)
        except Exception as exc:
            out["warnings"].append(f"drum notation failed: {exc}")
```

with:

```python
        try:
            bpm = grid.bpm if grid is not None else 120.0
            xml = drumnotation.render_drum_musicxml(midi, sdir / f"{stem_name}.musicxml", bpm=bpm)
            out["musicxml"] = storage.upload_artifact(xml, job_id)
            pdf = drumnotation.render_drum_pdf(midi, sdir / f"{stem_name}.pdf", bpm=bpm)
            out["sheet_pdf"] = storage.upload_artifact(pdf, job_id)
        except Exception as exc:
            out["warnings"].append(f"drum notation failed: {exc}")
```

- [ ] **Step 5: Detect tempo in `run_pipeline` and thread it through**

In `run_pipeline`, replace:

```python
        storage.update_job(job_id, status="processing", stage="downloading")
        wav = download.fetch_audio(source, is_url, work / "src", proxy)

        storage.update_job(job_id, stage="separating")
        separated = separate.separate(wav, work / "stems")

        results = []
        for name in stems:
            if name not in separated:
                continue
            storage.update_job(job_id, stage=f"transcribing:{name}")
            results.append(process_stem(name, separated[name], work / "out", job_id))
```

with:

```python
        storage.update_job(job_id, status="processing", stage="downloading")
        wav = download.fetch_audio(source, is_url, work / "src", proxy)

        try:
            grid = postprocess.detect_tempo(wav)
        except Exception:
            grid = None

        storage.update_job(job_id, stage="separating")
        separated = separate.separate(wav, work / "stems")

        results = []
        for name in stems:
            if name not in separated:
                continue
            storage.update_job(job_id, stage=f"transcribing:{name}")
            results.append(process_stem(name, separated[name], work / "out", job_id, grid=grid))
```

- [ ] **Step 6: Verify imports resolve and the suite stays green**

Run: `python -c "import pipeline.pipeline"`
Expected: no output, exit 0 (no import/syntax errors).

Run: `python -m pytest pipeline/tests -v`
Expected: PASS (all existing + new tests green).

- [ ] **Step 7: Commit**

```bash
git add pipeline/pipeline.py
git commit -m "feat(pipeline): detect tempo once and post-process each stem"
```

---

## Task 8: Wire post-processing into the Modal orchestrator

**Files:**
- Modify: `modal_app.py` (`process_job`, `transcribe_stem`)

> No new unit test: this is Modal glue verified by the import check below + Task 9 integration. `transcribe_stem` simply reconstructs a `Grid` from a serializable tuple and forwards it to the already-tested `process_stem`.

- [ ] **Step 1: Detect tempo in `process_job` and pass it to the fan-out**

In `modal_app.py`, change the `process_job` import line:

```python
    from pipeline import download, storage
```

to:

```python
    from pipeline import download, postprocess, storage
```

Then, in `process_job`, replace:

```python
        storage.update_job(job_id, stage="separating")
        stem_bytes = separate_audio.remote(wav.read_bytes())

        storage.update_job(job_id, stage="transcribing")
        available = [n for n in stems if n in stem_bytes]

        # MT3 is disabled in this deployment (see mt3_to_midi above): its JAX/T5X image
        # fails to build on Modal. Every stem — incl. guitar/piano — renders via the CPU
        # transcribe_stem path, which uses basic-pitch for the polyphonic stems.
        render_calls = [transcribe_stem.spawn(n, stem_bytes[n], job_id) for n in available]
```

with:

```python
        try:
            grid = postprocess.detect_tempo(wav)
            grid_tuple = (grid.bpm, grid.beat_offset)
        except Exception:
            grid_tuple = None

        storage.update_job(job_id, stage="separating")
        stem_bytes = separate_audio.remote(wav.read_bytes())

        storage.update_job(job_id, stage="transcribing")
        available = [n for n in stems if n in stem_bytes]

        # MT3 is disabled in this deployment (see mt3_to_midi above): its JAX/T5X image
        # fails to build on Modal. Every stem — incl. guitar/piano — renders via the CPU
        # transcribe_stem path, which uses basic-pitch for the polyphonic stems.
        render_calls = [transcribe_stem.spawn(n, stem_bytes[n], job_id, None, grid_tuple)
                        for n in available]
```

- [ ] **Step 2: Accept + forward the grid in `transcribe_stem`**

Change the `transcribe_stem` signature:

```python
@app.function(image=image, timeout=1800, secrets=secrets)
def transcribe_stem(stem_name: str, wav_bytes: bytes, job_id: str,
                    midi_bytes: bytes | None = None) -> dict:
```

to:

```python
@app.function(image=image, timeout=1800, secrets=secrets)
def transcribe_stem(stem_name: str, wav_bytes: bytes, job_id: str,
                    midi_bytes: bytes | None = None,
                    grid: tuple | None = None) -> dict:
```

Then replace the body's tail:

```python
    from pipeline.pipeline import process_stem

    work = Path(tempfile.mkdtemp())
    wav = work / f"{stem_name}.wav"
    wav.write_bytes(wav_bytes)
    precomputed = None
    if midi_bytes is not None:
        precomputed = work / f"{stem_name}.in.mid"
        precomputed.write_bytes(midi_bytes)
    return process_stem(stem_name, wav, work / "out", job_id, precomputed_midi=precomputed)
```

with:

```python
    from pipeline.pipeline import process_stem
    from pipeline.postprocess import Grid

    work = Path(tempfile.mkdtemp())
    wav = work / f"{stem_name}.wav"
    wav.write_bytes(wav_bytes)
    precomputed = None
    if midi_bytes is not None:
        precomputed = work / f"{stem_name}.in.mid"
        precomputed.write_bytes(midi_bytes)
    grid_obj = Grid(*grid) if grid is not None else None
    return process_stem(stem_name, wav, work / "out", job_id,
                        precomputed_midi=precomputed, grid=grid_obj)
```

- [ ] **Step 3: Verify the module parses**

Run: `python -c "import ast; ast.parse(open('modal_app.py').read())"`
Expected: no output, exit 0 (no syntax errors). (A full `import modal_app` requires the `modal` package; the `ast.parse` check is sufficient for syntax.)

- [ ] **Step 4: Commit**

```bash
git add modal_app.py
git commit -m "feat(modal): detect tempo in process_job, thread grid into transcribe_stem"
```

---

## Task 9: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole dependency-light suite**

Run: `python -m pytest pipeline/tests -v`
Expected: all pass (pre-existing 13 + new postprocess tests; pretty_midi/music21-guarded tests pass or skip depending on local deps).

- [ ] **Step 2: Confirm both orchestrators import / parse**

Run: `python -c "import pipeline.pipeline"`
Run: `python -c "import ast; ast.parse(open('modal_app.py').read())"`
Expected: both exit 0.

- [ ] **Step 3: Integration on Modal (real audio) — record the result**

Deploy and run a real job (per the deployment notes; on Windows set `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` first):

```bash
modal deploy modal_app.py
```

Then submit a short clip at a **known, non-120 tempo** through the web UI (or `modal run modal_app.py::process_job ...`). Verify against the design's success criteria:
- the drum chart's bar/rhythm matches the song's tempo (not 120 BPM);
- bass/vocals scores have no overlapping "ghost" notes and read cleanly on the beat;
- scores show a key signature instead of a wall of accidentals;
- no stem is dropped — any post-processing failure surfaces only as a warning.

- [ ] **Step 4: Final confirmation**

Confirm the branch `transcription-accuracy-postprocess` contains the 8 task commits and the design doc, and report integration results to the user before any merge.

---

## Notes / deliberate scope boundaries (from the spec)

- **No new ML models / no GPU change.** Guitar/piano *pitch* accuracy is not fundamentally improved — they gain clean rhythm + notation only. (Future "scope C": pYIN for bass/vocals, or re-enabling MT3.)
- **No pitch snapping to key** — key signature is spelling/readability only.
- **No time-signature detection** — 4/4 assumed.
- **Constant tempo only** — a uniform global-BPM grid; songs with genuine tempo changes will drift.
