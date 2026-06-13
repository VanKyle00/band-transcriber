# alphaTab Interactive Tab Rendering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every guitar/bass stem's tab as an interactive alphaTab staff in the browser, driven by an AlphaTex artifact the pipeline emits from the exact fret positions it already computes.

**Architecture:** `tab.py` gains an AlphaTex renderer beside its ASCII one; both derive from the same `placements`, so the fallback ASCII view and the alphaTab view never disagree. `process_stem` uploads a new `.alphatex` artifact alongside the `.tab.txt`. The web `Tab` component renders AlphaTex via alphaTab when present, else the existing `<pre>` ASCII.

**Tech Stack:** Python (pytest, dependency-light — no ML deps needed for these tests), Next.js 15 / React 19 / TypeScript, `@coderline/alphatab@1.8.3`.

**Spec:** `docs/superpowers/specs/2026-06-13-alphatab-tab-rendering-design.md`

> **Note — git:** This project is not currently a git repository. The `Commit` steps below assume you have run `git init` (or are otherwise under version control). If not, skip the commit steps.

> **Note — AlphaTex dialect (verified against docs):** alphaTab 1.8 omits the legacy `.` metadata separator. String 1 is the **highest-pitched** string (the doc chord `(0.1 2.2 2.3 2.4 0.5)` is an open A‑major). alphaTab's tuning octave is **one above scientific** (`octave = midi // 12`), so `GUITAR_TUNING` reversed renders as `E5 B4 G4 D4 A3 E3` — matching the docs' own standard-guitar example. Our low-string-first index `idx` maps to AlphaTex string `n - idx`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `pipeline/tab.py` | Modify | Add `_alphatab_pitch`, `render_alphatex`, `_read_midi_notes`, `midi_to_tabs`; refactor `midi_to_ascii_tab` onto the shared reader |
| `pipeline/tests/test_tab.py` | Modify | Deterministic tests for `render_alphatex` (no ML deps) |
| `pipeline/storage.py` | Modify | Map `.alphatex` → `text/plain` |
| `pipeline/pipeline.py` | Modify | `_build_tab` returns `(ascii, alphatex, warn)`; `process_stem` emits `tab_alphatex` |
| `pipeline/tests/test_pipeline.py` | Create | Dependency-light tests for `_build_tab` + `process_stem` wiring + storage MIME |
| `apps/web/lib/types.ts` | Modify | Add `tab_alphatex?` to `StemArtifacts` |
| `apps/web/package.json` | Modify | Add `@coderline/alphatab@1.8.3` |
| `apps/web/components/Tab.tsx` | Modify | alphaTab rendering path + ASCII fallback |
| `apps/web/components/StemPanel.tsx` | Modify | Show Tab view when either `tab` or `tab_alphatex` is present |

---

## Task 1: AlphaTex renderer in `tab.py`

**Files:**
- Modify: `pipeline/tab.py`
- Test: `pipeline/tests/test_tab.py`

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `pipeline/tests/test_tab.py` (line 8) `render_alphatex`:

```python
from pipeline.tab import _placements, assign_columns, notes_to_tab, render_alphatex, render_tab
```

Append these tests before the `if __name__ == "__main__":` block:

```python
def test_render_alphatex_header_and_single_note():
    # idx 0 is the low-E string -> AlphaTex string 6. Tuning lists high->low,
    # alphaTab octave = midi // 12 (one above scientific).
    tex = render_alphatex([{0: 0}], GUITAR_TUNING)
    assert tex == "\\tuning E5 B4 G4 D4 A3 E3\n:4 0.6"


def test_render_alphatex_string_numbering():
    # Low-E string (idx 0) -> string 6; high-E string (idx 5) -> string 1.
    assert render_alphatex([{0: 3}], GUITAR_TUNING).endswith("3.6")
    assert render_alphatex([{5: 0}], GUITAR_TUNING).endswith("0.1")


def test_render_alphatex_chord():
    # A column with several strings becomes a parenthesised beat, low string first.
    tex = render_alphatex([{0: 0, 1: 2, 2: 2}], GUITAR_TUNING)
    assert "(0.6 2.5 2.4)" in tex


def test_render_alphatex_empty_column_is_rest():
    assert render_alphatex([{}], GUITAR_TUNING).endswith(":4 r")


def test_render_alphatex_inserts_barlines():
    # 5 beats at 4 beats/bar -> exactly one bar separator.
    tex = render_alphatex([{0: 0}] * 5, GUITAR_TUNING)
    assert tex.count(" | ") == 1


def test_render_alphatex_bass_tuning():
    tex = render_alphatex([{0: 0}], BASS_TUNING)
    assert tex == "\\tuning G3 D3 A2 E2\n:4 0.4"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest pipeline/tests/test_tab.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_alphatex' from 'pipeline.tab'`

- [ ] **Step 3: Implement the renderer**

In `pipeline/tab.py`, add `_alphatab_pitch` just after `_pitch_letter` (after line 16):

```python
def _alphatab_pitch(midi: int) -> str:
    """alphaTab note name: letter + alphaTab octave (= midi // 12, one above
    scientific pitch — matches alphaTab's `\\tuning` convention)."""
    return f"{_PITCH_LETTERS[midi % 12]}{midi // 12}"
```

Add `render_alphatex` after `render_tab` (after line 101):

```python
def render_alphatex(placements: list[dict[int, int]], tuning: list[int],
                    beats_per_bar: int = 4) -> str:
    """Render assigned columns as AlphaTex (alphaTab's text format).

    AlphaTex string 1 is the highest-pitched string, so our low-string-first
    index `idx` maps to AlphaTex string `n - idx`; the tuning is listed high->low.
    Durations are fixed at one quarter-note beat per column (same fidelity as the
    ASCII tab); a column with no playable note becomes a rest.
    """
    n = len(tuning)
    names = " ".join(_alphatab_pitch(tuning[i]) for i in range(n - 1, -1, -1))

    beats: list[str] = []
    for col in placements:
        if not col:
            beats.append("r")
            continue
        notes = [f"{fret}.{n - idx}" for idx, fret in sorted(col.items())]
        beats.append(notes[0] if len(notes) == 1 else "(" + " ".join(notes) + ")")

    if not beats:
        beats = ["r"]
    bars = [" ".join(beats[i:i + beats_per_bar])
            for i in range(0, len(beats), beats_per_bar)]
    return f"\\tuning {names}\n:4 " + " | ".join(bars)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_tab.py -q`
Expected: PASS — all tests (existing 8 + new 6).

- [ ] **Step 5: Add the shared MIDI reader and `midi_to_tabs`**

Still in `pipeline/tab.py`, replace the existing `midi_to_ascii_tab` (lines 111-121) with a shared reader plus both renderers:

```python
def _read_midi_notes(midi_path: str) -> list[tuple[float, int]]:
    """Read (start_seconds, pitch) for all non-drum notes. Requires pretty_midi."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(midi_path)
    return [
        (note.start, note.pitch)
        for inst in pm.instruments if not inst.is_drum
        for note in inst.notes
    ]


def midi_to_ascii_tab(midi_path: str, tuning: list[int]) -> str:
    """Read a MIDI file and produce ASCII tab."""
    return notes_to_tab(_read_midi_notes(midi_path), tuning)


def midi_to_tabs(midi_path: str, tuning: list[int]) -> tuple[str, str]:
    """Read a MIDI file once; return (ascii_tab, alphatex) from the same placements."""
    columns = _group_columns(_read_midi_notes(midi_path))
    placements = assign_columns(columns, tuning)
    return render_tab(placements, tuning), render_alphatex(placements, tuning)
```

- [ ] **Step 6: Run the full tab suite again**

Run: `python -m pytest pipeline/tests/test_tab.py -q`
Expected: PASS (no regressions — `midi_to_ascii_tab` behavior is unchanged).

- [ ] **Step 7: Commit**

```bash
git add pipeline/tab.py pipeline/tests/test_tab.py
git commit -m "feat(pipeline): render AlphaTex tab alongside ASCII"
```

---

## Task 2: Emit the `tab_alphatex` artifact (`pipeline.py` + `storage.py`)

**Files:**
- Modify: `pipeline/storage.py:17-22`
- Modify: `pipeline/pipeline.py:18-36` (`_build_tab`), `pipeline/pipeline.py:79-86` (`process_stem`)
- Test: `pipeline/tests/test_pipeline.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest pipeline/tests/test_pipeline.py -q`
Expected: FAIL — `test_storage_maps_alphatex_to_text` fails (returns `application/octet-stream`) and `test_process_stem_emits_tab_alphatex` fails with `KeyError: 'tab_alphatex'`.

- [ ] **Step 3: Add the `.alphatex` MIME entry**

In `pipeline/storage.py`, add to the `_MIME` dict (after line 21, inside the literal):

```python
    ".xml": "application/xml", ".txt": "text/plain", ".json": "application/json",
    ".alphatex": "text/plain",
```

- [ ] **Step 4: Update `_build_tab` to return a 3-tuple**

Replace `pipeline/pipeline.py` lines 18-36 (`_build_tab`) with:

```python
def _build_tab(stem_name: str, midi: Path, spec) -> tuple[str | None, str | None, str | None]:
    """Generate tab for a stem. Returns (ascii_tab, alphatex, warning).

    Uses open-fret's learned fingering when configured + available (ASCII only for
    now — see the design's non-goals), falling back to the deterministic assigner
    which produces both ASCII and AlphaTex. (None, None, warning) only if even the
    fallback fails.
    """
    if stem_name in OPENFRET_STEMS and opentab.available():
        try:
            return opentab.midi_to_tab_openfret(midi), None, None
        except Exception as exc:
            warn = f"open-fret failed, used heuristic tab: {exc}"
            try:
                return tab.midi_to_ascii_tab(str(midi), spec.tuning), None, warn
            except Exception as exc2:
                return None, None, f"tab failed: {exc2}"
    try:
        ascii_tab, alphatex = tab.midi_to_tabs(str(midi), spec.tuning)
        return ascii_tab, alphatex, None
    except Exception as exc:
        return None, None, f"tab failed: {exc}"
```

- [ ] **Step 5: Update `process_stem` to upload the AlphaTex artifact**

Replace `pipeline/pipeline.py` lines 79-86 (the `if "tab" in spec.outputs ...` block) with:

```python
    if "tab" in spec.outputs and spec.tuning:
        ascii_tab, alphatex, warn = _build_tab(stem_name, midi, spec)
        if ascii_tab is not None:
            tab_txt = sdir / f"{stem_name}.tab.txt"
            tab_txt.write_text(ascii_tab, encoding="utf-8")
            out["tab"] = storage.upload_artifact(tab_txt, job_id)
        if alphatex is not None:
            tab_tex = sdir / f"{stem_name}.alphatex"
            tab_tex.write_text(alphatex, encoding="utf-8")
            out["tab_alphatex"] = storage.upload_artifact(tab_tex, job_id)
        if warn:
            out["warnings"].append(warn)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS — the new `test_pipeline.py` tests plus all existing tests (`test_tab.py`, `test_config.py`).

- [ ] **Step 7: Commit**

```bash
git add pipeline/pipeline.py pipeline/storage.py pipeline/tests/test_pipeline.py
git commit -m "feat(pipeline): upload .alphatex artifact next to ASCII tab"
```

---

## Task 3: Expose `tab_alphatex` to the web app + install alphaTab

**Files:**
- Modify: `apps/web/lib/types.ts:1-10`
- Modify: `apps/web/package.json:11-18`

- [ ] **Step 1: Add the field to the artifact type**

In `apps/web/lib/types.ts`, add to `StemArtifacts` (after line 9, `tab?: string;`):

```typescript
  tab?: string;
  tab_alphatex?: string;
```

- [ ] **Step 2: Install alphaTab (pinned)**

Run:

```bash
cd apps/web && npm install @coderline/alphatab@1.8.3
```

Expected: `package.json` now lists `"@coderline/alphatab": "1.8.3"` under `dependencies`; `package-lock.json` updates.

- [ ] **Step 3: Verify types still compile**

Run: `cd apps/web && npx tsc --noEmit`
Expected: PASS (no type errors).

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/types.ts apps/web/package.json apps/web/package-lock.json
git commit -m "feat(web): add tab_alphatex artifact type and alphaTab dependency"
```

---

## Task 4: Render AlphaTex with alphaTab in the UI

**Files:**
- Modify: `apps/web/components/Tab.tsx` (full rewrite)
- Modify: `apps/web/components/StemPanel.tsx:14-18`, `:59`

- [ ] **Step 1: Rewrite `Tab.tsx` with an alphaTab path and ASCII fallback**

Replace the entire contents of `apps/web/components/Tab.tsx` with:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { AlphaTabApi } from "@coderline/alphatab";

// Tab renders two ways:
//  - if an AlphaTex artifact exists, alphaTab engraves an interactive staff + tab
//  - otherwise we fall back to the server-generated ASCII tab in a <pre>
export default function Tab({ url, alphatexUrl }: { url?: string; alphatexUrl?: string }) {
  if (alphatexUrl) return <AlphaTexTab url={alphatexUrl} />;
  if (url) return <AsciiTab url={url} />;
  return null;
}

function AsciiTab({ url }: { url: string }) {
  const [text, setText] = useState("Loading tab…");
  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((r) => r.text())
      .then((t) => !cancelled && setText(t))
      .catch(() => !cancelled && setText("Failed to load tab."));
    return () => {
      cancelled = true;
    };
  }, [url]);
  return <pre className="tab">{text}</pre>;
}

// alphaTab is a browser-only library; load it inside the effect so it never runs
// during SSR. useWorkers:false keeps rendering on the main thread (no worker asset
// wiring), and the SMuFL font is loaded from the pinned CDN build. Player is off.
function AlphaTexTab({ url }: { url: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let api: AlphaTabApi | undefined;

    (async () => {
      try {
        const tex = await (await fetch(url)).text();
        if (cancelled || !ref.current) return;
        const alphaTab = await import("@coderline/alphatab");
        api = new alphaTab.AlphaTabApi(ref.current, {
          core: {
            useWorkers: false,
            fontDirectory:
              "https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.8.3/dist/font/",
          },
          player: { enablePlayer: false },
        });
        api.tex(tex);
      } catch {
        if (!cancelled) setError("Failed to render tab.");
      }
    })();

    return () => {
      cancelled = true;
      api?.destroy();
    };
  }, [url]);

  if (error) return <pre className="tab">{error}</pre>;
  return <div className="alphatab" ref={ref} />;
}
```

- [ ] **Step 2: Wire `StemPanel` to show Tab when either artifact exists**

In `apps/web/components/StemPanel.tsx`, change the `available` list entry (line 16) from:

```tsx
    stem.tab ? ("tab" as const) : null,
```

to:

```tsx
    stem.tab || stem.tab_alphatex ? ("tab" as const) : null,
```

And change the Tab render (line 59) from:

```tsx
      {view === "tab" && stem.tab && <Tab url={stem.tab} />}
```

to:

```tsx
      {view === "tab" && (stem.tab || stem.tab_alphatex) && (
        <Tab url={stem.tab} alphatexUrl={stem.tab_alphatex} />
      )}
```

- [ ] **Step 3: Verify the type-check passes**

Run: `cd apps/web && npx tsc --noEmit`
Expected: PASS. `AlphaTabApi` is brought in via `import type` (erased at runtime, so it never evaluates the browser-only module during SSR). If the settings object argument is flagged by tsc, append ` as any` to the settings object literal — alphaTab accepts the JSON settings form at runtime.

- [ ] **Step 4: Verify the production build passes**

Run: `cd apps/web && npx next build`
Expected: build succeeds. alphaTab is dynamically imported inside an effect, so it is never evaluated during SSR/prerender.

- [ ] **Step 5: Manual verification**

Run `cd apps/web && npm run dev`, submit a short clip (or open an existing job with a guitar/bass stem), open the stem's **Tab** view, and confirm an engraved staff + tablature appears (not raw text) and the fret numbers match the downloadable ASCII `.tab.txt`.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/Tab.tsx apps/web/components/StemPanel.tsx
git commit -m "feat(web): render interactive tab via alphaTab with ASCII fallback"
```

---

## Known considerations (not blocking)

- **Long tracks:** an 8-minute song produces many bars rendered synchronously (`useWorkers:false`). If rendering feels slow, enabling alphaTab workers is a later optimization.
- **open-fret path:** stays ASCII-only by design (its stdout mixes AlphaTex + preview with no documented delimiter, and it's dormant). Splitting it into a clean `tab_alphatex` is a future follow-up.
- **No playback:** alphaTab's player is disabled here; in-browser tab audio overlaps the separate "piano-roll audio" deferred task.

---

## Self-Review

**1. Spec coverage:**
- Interactive tab for all guitar/bass today → Task 1 (renderer) + Task 2 (artifact) + Task 4 (render). ✓
- Preserve computed frets (AlphaTex from `placements`) → Task 1 `render_alphatex`/`midi_to_tabs`. ✓
- ASCII fallback retained (view + download) → Task 4 `AsciiTab`; StemPanel download link unchanged. ✓
- New manifest field + types → Task 2 (`out["tab_alphatex"]`) + Task 3 (`types.ts`). ✓
- alphaTab integration (client-only, no workers, font, no player) → Task 4. ✓
- open-fret ASCII-only / no playback / no rhythm non-goals → preserved in `_build_tab`, fixed `:4` duration, player off. ✓
- Python deterministic renderer test + frontend build/manual → Task 1 tests, Task 4 build/manual. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every command states expected output. ✓

**3. Type consistency:** `render_alphatex(placements, tuning, beats_per_bar=4)`, `midi_to_tabs(midi_path, tuning) -> (ascii, alphatex)`, `_build_tab(...) -> (ascii|None, alphatex|None, warn|None)`, and `out["tab_alphatex"]` ↔ `tab_alphatex?` in `types.ts` ↔ `alphatexUrl` prop are used consistently across tasks. ✓
