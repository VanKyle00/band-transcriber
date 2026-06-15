# Transcription accuracy: post-processing layer — design

**Date:** 2026-06-15
**Status:** Approved (pre-implementation)

## Overview

Transcriptions read as broadly inaccurate — wrong rhythm, junk notes, unreadable
notation, and some wrong pitches — across every instrument. The root cause is largely
**structural, not the pitch models**: there is no tempo detection and no rhythmic
quantization anywhere. `basic-pitch`'s raw MIDI is rendered straight to notation, and
the drum chart hardcodes `_ASSUMED_BPM = 120`. Any song not at 120 BPM gets wrong note
durations and drifting bars even when the pitches are correct.

This adds a cheap, CPU-only **post-processing layer** between transcription and notation:
detect the real tempo once per song, quantize each stem's notes to a beat grid, clean up
spurious notes, and add a key signature for readable spelling. No new ML models, no GPU,
no change to per-song cost. (Scope "A" from brainstorming — heavier model upgrades like
re-enabling MT3 or higher-quality separation were explicitly deferred to keep cost flat.)

## Goal & success criteria

- A song at a non-120 tempo produces notation whose bars and note durations line up to
  the actual beat (verified by ear / against a known-tempo reference clip).
- Monophonic stems (bass, vocals) no longer carry overlapping "ghost" notes; ultra-short
  spurious notes are gone across all stems.
- Scores render with a detected key signature instead of a wall of accidentals.
- The drum chart's tempo matches the song instead of a fixed 120 BPM.
- Post-processing **never sinks a job**: any failure falls back to today's behavior with a
  recorded warning.
- `python -m pytest pipeline/tests` passes, including new **dependency-light** tests for
  the quantize/clean core (no ML deps, matching the existing suite).

## Current state

- `pipeline/transcribe/melodic.py` writes `basic-pitch`'s raw MIDI directly — no tempo,
  no grid-snapping, no cleanup.
- `pipeline/transcribe/drums.py` emits onsets with a fixed 50 ms duration, no tempo.
- `pipeline/drumnotation.py:24` hardcodes `_ASSUMED_BPM = 120` and forces 4/4.
- `pipeline/notation.py` does `converter.parse(midi)` with no key signature and no
  tempo/beat alignment.
- Orchestration: both `modal_app.py::process_job` and `pipeline/pipeline.py::run_pipeline`
  hold the full-mix `wav` *before* stem fan-out, then call `process_stem` per stem
  (`transcribe_stem.spawn` on Modal). This is the natural place to detect tempo once.

## Design

### Data flow

```
full-mix wav ─► detect_tempo(wav) ─► Grid(bpm, beat_offset)   [ONCE per song]
                                          │  (threaded into each stem)
process_stem(stem, wav, …, grid):
   transcribe → MIDI
     melodic stem ─► quantize_and_clean(MIDI, grid, monophonic=not spec.polyphonic) ─┐
     drum stem    ─► (MIDI unchanged) ───────────────────────────────────────────────┤
                                                                                      ▼
   notation.midi_to_musicxml(MIDI, clef, +key signature)   |   drumnotation(MIDI, bpm=grid.bpm)
```

Tempo is detected on the **mix**, not per stem, so every stem snaps to the same grid and
their bars align. Demucs preserves timing, so mix-derived beats apply directly to stems.

### New module: `pipeline/postprocess.py`

Split into a pure-logic core (unit-testable with **zero ML deps**) and a thin I/O adapter:

1. **`detect_tempo(wav) -> Grid`** (the only audio/librosa-touching function)
   - librosa `beat_track` on the mix → global BPM + first-beat time.
   - **Half/double-tempo guard:** fold BPM into a sane range (60–180) by doubling/halving
     — librosa's classic failure mode.
   - Returns a small `Grid` dataclass `(bpm: float, beat_offset: float)` describing a
     **uniform** constant-tempo grid. Two floats — trivially serializable across Modal.

2. **`quantize_and_clean(notes, grid, *, monophonic, subdiv=4) -> notes`** (pure logic)
   - Operates on a plain list of `Note(start, end, pitch, velocity)` tuples — **no
     `pretty_midi` import in the core**, so it tests without ML deps.
   - Grid spacing = `(60 / bpm) / subdiv` seconds (16th-note grid by default), anchored at
     `beat_offset`.
   - Steps, in order:
     1. snap each note's start and end to the nearest grid line (minimum one slot long);
     2. drop notes shorter than half a slot (spurious);
     3. merge consecutive same-pitch notes separated by < one slot;
     4. if `monophonic`: resolve overlaps by keeping the longer/louder note, truncating
        or dropping the other.

3. **`apply_to_midi(midi_path, grid, *, monophonic) -> midi_path`** — thin `pretty_midi`
   adapter: read notes → `quantize_and_clean` → set the MIDI tempo to `grid.bpm` → write
   back. (Setting the tempo to match grid-aligned times makes music21 read clean quarter
   lengths.)

### Tempo threading (orchestration edits)

- **`pipeline/pipeline.py::run_pipeline`**: after `download.fetch_audio`, call
  `detect_tempo(wav)` once; pass the resulting `grid` into each `process_stem`.
- **`modal_app.py::process_job`**: after obtaining `wav`, call `detect_tempo(wav)` and
  pass `(bpm, beat_offset)` into each `transcribe_stem.spawn(...)`.
- **`modal_app.py::transcribe_stem`** and **`pipeline/pipeline.py::process_stem`**: gain a
  `grid` parameter (default `None`). When `None` (e.g. detection failed), behavior is
  exactly as today.

### Per-stem wiring (`process_stem`)

- **Melodic stems** (bass, vocals, guitar, piano): after `transcribe()` writes the MIDI,
  call `postprocess.apply_to_midi(midi, grid, monophonic=not spec.polyphonic)`. Notation
  and tab then proceed on the cleaned MIDI exactly as today.
- **Drums:** pass `grid.bpm` into `drumnotation.render_drum_musicxml` / `render_drum_pdf`,
  replacing the hardcoded `_ASSUMED_BPM`. The drum slot-quantizer is otherwise unchanged.

### Notation readability (`notation.py`)

`midi_to_musicxml` gains a key-signature step: `score.analyze('key')` → insert the
detected `KeySignature` so notes spell with proper sharps/flats. **Pitches are not
changed** — no snapping into the key (snapping risks introducing wrong notes). Time
signature stays **4/4**.

### Error handling

Consistent with the existing "per-output failures become warnings" philosophy:
- If `detect_tempo` fails or returns an out-of-range/garbage tempo, `grid` is `None` and
  every stem falls back to today's behavior (no quantization; drums use 120 BPM). Record a
  job-level warning.
- If `apply_to_midi` raises, keep the original (un-quantized) MIDI and add a per-stem
  warning — never block notation/tab.
- If `score.analyze('key')` fails, render without a key signature (today's behavior).

## Non-goals / deliberate scope boundaries

- **No new ML models / no GPU change.** MT3 stays disabled; separation stays `htdemucs_6s`.
  Guitar/piano *pitch* accuracy is therefore not fundamentally improved — they get cleaner
  rhythm and notation only. (A future "scope C": pYIN for bass/vocals, or re-enabling MT3.)
- **No pitch snapping to key.** Key signature is for spelling/readability only.
- **No time-signature detection.** 4/4 is assumed (correct for the vast majority of songs;
  detection is error-prone).
- **Constant tempo only.** A uniform global-BPM grid; songs with genuine tempo changes
  (rare in pop/rock) will drift. Chosen for far cleaner notation.

## Testing & verification

- **Python (`pipeline/tests/test_postprocess.py`, new)** — dependency-light, no ML deps:
  - grid-snapping rounds onsets/durations to the expected slots;
  - notes shorter than half a slot are dropped;
  - consecutive same-pitch notes within a slot merge;
  - monophony resolution removes overlaps (keeps longer/louder);
  - the half/double-tempo guard folds BPM into 60–180.
- **Existing suite** (`python -m pytest pipeline/tests`) stays green.
- **Integration (local/Modal, real stems):** a clip at a known non-120 tempo quantizes
  sensibly; the drum chart tempo matches; bass/vocals lose ghost notes.
- **Web end-to-end:** submit a short clip; confirm sheet/tab/piano-roll still render and
  the rhythm visibly lines up to the beat.

## Files touched

- `pipeline/postprocess.py` — **new**: `detect_tempo`, `quantize_and_clean`, `apply_to_midi`.
- `pipeline/pipeline.py` — `run_pipeline` detects tempo; `process_stem` gains `grid`,
  calls `apply_to_midi` for melodic stems and passes `bpm` to drum notation.
- `pipeline/drumnotation.py` — `render_drum_musicxml` / `render_drum_pdf` / `_slots` accept
  a `bpm` argument (default 120 preserves current behavior).
- `pipeline/notation.py` — `midi_to_musicxml` inserts a detected key signature.
- `modal_app.py` — `process_job` detects tempo and threads `grid` into `transcribe_stem`;
  `transcribe_stem` forwards `grid` to `process_stem`.
- `pipeline/tests/test_postprocess.py` — **new**: dependency-light quantize/clean tests.
