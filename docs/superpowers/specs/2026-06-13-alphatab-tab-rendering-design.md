# alphaTab interactive tab rendering — design

**Date:** 2026-06-13
**Status:** Approved (pre-implementation)

## Overview

Replace the plain-text (`<pre>`) tablature view with interactive, properly-engraved
tab rendered by [alphaTab](https://alphatab.net). It must work for **every guitar and
bass stem produced today** — not gated on open-fret (which is dormant: no public
weights). The fret positions the pipeline computes are preserved; alphaTab renders
exactly what `tab.py` (or, later, open-fret) chose rather than re-fretting on its own.

## Goal & success criteria

- Submitting a clip and opening a guitar or bass **Tab** view shows a rendered staff +
  tablature (alphaTab), not raw ASCII.
- The rendered frets match the pipeline's assignment; the ASCII view (still available as
  a download and as a fallback) agrees with it because both derive from the same data.
- `python -m pytest pipeline/tests` passes, including a new deterministic test for the
  AlphaTex renderer (no ML deps required).
- `cd apps/web && npx tsc --noEmit && npx next build` passes.

## Current state

- `pipeline/pipeline.py` `process_stem` writes **one** tab artifact per stem
  (`out["tab"]` → a `.tab.txt`). Content depends on the generator:
  - `pipeline/tab.py` (deterministic assigner, default) → **ASCII** tab.
  - `pipeline/opentab.py` (open-fret) → **AlphaTex + ASCII preview** in one stdout blob;
    dormant because no weights ship.
- `apps/web/components/Tab.tsx` fetches that text and dumps it in a `<pre>`.
- Guitar and bass also already produce **MIDI** and **MusicXML** artifacts.

## Design

### Data flow

```
guitar/bass MIDI ─► tab.py ─┬─ render_tab      → .tab.txt   (ASCII, unchanged)
                            └─ render_alphatex  → .alphatex  (NEW)
                                   │
process_stem stores both ─► manifest: { tab, tab_alphatex } ─► StemPanel
                                   │
Tab.tsx: tab_alphatex? → <AlphaTab> (interactive)   else → <pre> ASCII (fallback)
```

Both renderings come from the **same** `placements` (computed once), so the ASCII
fallback and the alphaTab view never disagree on fingering.

### Pipeline (Python)

1. **`tab.py`: add `render_alphatex(placements, tuning, beats_per_bar=4)`** beside
   `render_tab`, consuming the same column/placement model and emitting AlphaTex:
   - Header: `\tuning <names high→low>` then `.` to close metadata; `:4` default duration.
   - Each column → one beat: single note `fret.string`; chord `(f.s f.s ...)`; empty
     column → rest `r`.
   - String mapping: pipeline `tuning` is lowest-string-first (index 0 = lowest pitch);
     AlphaTex string number = `n - index` (AlphaTex string 1 = highest pitch). Tuning
     names listed high→low to match.
   - MIDI→scientific note name (e.g. `40 → E2`) reuses the existing `_PITCH_LETTERS`
     table; octave = `midi // 12 - 1`.
   - Insert a bar line `|` every `beats_per_bar` beats (default 4/4).
   - Durations are fixed (one beat per column) — identical fidelity to today's ASCII
     tab. Deriving real rhythm from onset timing is an explicit **non-goal**.

2. **`tab.py`: add `midi_to_tabs(midi_path, tuning) -> (ascii, alphatex)`** that parses
   the MIDI once and renders both, so we don't read the file twice. (Existing
   `midi_to_ascii_tab` stays — it is still called by the open-fret fallback branch in
   `_build_tab`, which only needs ASCII.)

3. **`pipeline.py` `_build_tab`**: the heuristic path returns `(ascii, alphatex, warn)`;
   `process_stem` uploads `out["tab"]` (ASCII `.tab.txt`) **and** `out["tab_alphatex"]`
   (`.alphatex`). The open-fret branch is unchanged (see Non-goals).

### Frontend (Next.js)

4. **`apps/web/lib/types.ts`**: add `tab_alphatex?: string` to `StemArtifacts`.

5. **`apps/web/components/Tab.tsx`**: if an AlphaTex URL is present, fetch its text and
   render via alphaTab; otherwise keep the current ASCII `<pre>`. `StemPanel` shows the
   **Tab** view button when either `tab` or `tab_alphatex` is present; the ASCII "Tab"
   download link is retained.

6. **alphaTab integration** (`@coderline/alphatab`):
   - Client-only, dynamic import (avoid SSR; the lib touches `window`).
   - `core.useWorkers: false` — render on the main thread, no Next.js worker-asset wiring.
   - Bravura SMuFL font copied to `public/alphatab/font/`, referenced via
     `core.fontDirectory: '/alphatab/font/'` (CDN as fallback if asset copy is an issue).
   - Player **disabled** (render only).

## Non-goals / deliberate scope boundaries

- **open-fret path stays ASCII-only.** Its stdout is an AlphaTex+preview blob with no
  documented delimiter, and it's dormant (untestable without weights). v1 leaves it
  feeding the `tab` (ASCII → `<pre>`) slot so each stem keeps a single source of truth.
  Cleanly splitting open-fret's AlphaTex into `tab_alphatex` is a noted follow-up.
- **No in-browser playback.** alphaTab audio (SoundFont) overlaps the separate deferred
  "piano-roll audio" task and is out of scope here.
- **No rhythm inference.** Fixed one-beat-per-column durations, matching current tab
  fidelity.

## Testing & verification

- **Python (`pipeline/tests/test_tab.py`)**: add deterministic assertions on
  `render_alphatex` output for known `(placements, tuning)` inputs — tuning order,
  single note `fret.string`, chord grouping `( )`, rest `r`, and bar-line insertion.
  String-level assertions need no ML dependencies, matching the existing suite.
- **Frontend**: `npx tsc --noEmit && npx next build` succeed.
- **Manual**: submit a short clip; open a guitar/bass **Tab** view; confirm a rendered
  staff + tablature appears and the frets match the ASCII download.

## Files touched

- `pipeline/tab.py` — add `render_alphatex`, `midi_to_tabs`.
- `pipeline/pipeline.py` — `_build_tab` + `process_stem` emit/upload `tab_alphatex`.
- `pipeline/tests/test_tab.py` — new renderer tests.
- `apps/web/lib/types.ts` — `tab_alphatex?` field.
- `apps/web/components/Tab.tsx` — alphaTab rendering path + ASCII fallback.
- `apps/web/components/StemPanel.tsx` — show Tab view when either field present.
- `apps/web/package.json` — add `@coderline/alphatab`.
- `apps/web/public/alphatab/font/` — Bravura font assets (or CDN fallback).
