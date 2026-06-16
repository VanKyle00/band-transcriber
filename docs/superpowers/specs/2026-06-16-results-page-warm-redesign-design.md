# Results page — warm "Practice Buddy" redesign

_Design spec · 2026-06-16_

## Context

The band-transcriber job page is being migrated, piece by piece, to the warm
cream/orange "Practice Buddy" design (Direction 3 from the Claude Design mock the
user chose). The **loading screen** and the **"Slow it down" speed control** are
already shipped (commit `66e0f23`). This spec covers the remaining piece: the
**results page** (the `done` state of a job) — hero, instrument chips, a featured
practice card per stem, and a play-along bar.

The current results page (`JobView` `done` branch) renders a plain dark heading
plus one `StemPanel` per stem (each panel: view toggle for Sheet/Tab/Piano-roll,
the interactive viewer, the speed slider, download links, warnings).

### Key constraint discovered during brainstorming

The `jobs` table and the `artifacts` JSON contain **no song metadata** — no title,
artist, BPM, key, or duration. The pipeline *detects* tempo (`grid.bpm` in
`postprocess.detect_tempo`) and a key (inside `notation.py`), but neither is stored
on the job row or in the artifacts manifest the web app reads. The interactive
viewers (OSMD sheet with cursor, alphaTab tab, piano roll) are the functional core
and each depend on their `<audio>` element for cursor/playhead sync.

### Decision (from brainstorming)

**Hybrid:** build the full warm layout now with graceful degradation, AND add the
one cheap backend win — store the already-detected `grid.bpm` into the artifacts so
the BPM chip and metronome are real. Title/artist/key stay soft (omitted) for a
later follow-up. Chosen approach: **a new `PracticeResults` component that reuses
the existing interactive players** (leaves the hard, working cursor-sync code
untouched).

## Goal

Faithfully render the Practice Buddy results layout, wired to the app's real
artifacts, with everything that depends on missing data degrading gracefully.

Success criteria:
- A finished job renders hero → chips → practice card → play-along bar in the warm
  theme, driven by the real stems and artifacts.
- Selecting an instrument chip swaps the focused stem instantly.
- The speed slider, loop, downloads, and the interactive viewers all work for the
  selected stem.
- When `artifacts.meta.bpm` is present, the BPM chip shows and the metronome +
  beat dots run in sync; when absent (old jobs), they are simply omitted — no
  errors, no fake values.

## Architecture

New `apps/web/components/PracticeResults.tsx`, rendered by `JobView` in place of
the current `done` branch (the loading and error branches are unchanged). It owns
one piece of state: `selectedStem` (defaults to the first available stem). It reads
`job.artifacts.stems` and `job.artifacts.meta`.

The existing `StemPanel.tsx` is **superseded** by the practice card for the
selected stem. Its internals (available-views computation, the Sheet/Tab/Roll
toggle, the players, the speed slider, downloads, warnings) move into
`PracticeResults` / a `PracticeCard` sub-piece. `StemPanel.tsx` is removed once
nothing imports it. The three player components (`PianoRoll`, `SheetMusic`, `Tab`)
and `lib/usePlaybackRate.ts` are reused as-is, with one new shared concern (see
Play-along bar) for play/pause + loop.

Component breakdown:
- `PracticeResults` — owns `selectedStem`; renders the four sections; holds the
  shared `<audio>`-driving state (play/pause, loop, speed) and the metronome.
- Hero — presentational, fed `{ bpm?, partCount, durationSec? }`.
- Chips — presentational, fed `stems` + `selectedStem` + `onSelect`.
- Practice card — the selected stem's viewer + controls.
- Play-along bar — transport for the selected stem's audio.

These can be one file initially (`PracticeResults.tsx`) with small internal
components; split out only if the file grows unwieldy.

## Section detail

### 1. Hero (graceful)

Warm gradient banner (`linear-gradient(135deg,#FBE3CC,#FBD7BE)`), the 🌼 mascot
tile, the "LET'S PRACTICE TOGETHER" eyebrow, and the headline **"Let's learn this
track, one part at a time."** (no song title — we don't have one). Meta chips,
each rendered only when its data exists:
- **♩ {bpm} BPM** — from `artifacts.meta.bpm`; omitted if absent.
- **{N} parts** — `stems.length`; always present.
- **{m:ss}** — track duration, read for free on the client from the selected
  stem's audio `loadedmetadata.duration` (all stems share the song length);
  omitted until known.

No artist, key, or duration-from-backend chips.

### 2. Instrument chips

"Which part do you want to play today?" then a pill per real stem. Each chip shows
a color dot (color mapped by stem name — vocals/guitar/bass/drums/piano — with a
neutral fallback for any other name) and the capitalized stem name. The selected
chip is filled with its color; others are cream outlines. Clicking sets
`selectedStem`. Switching stems resets transient transport state (pause, etc.).

### 3. Practice card

For the selected stem:
- Header: color dot + capitalized name + a short friendly note (static copy keyed
  by stem name; neutral fallback), an `experimental` badge if the stem is
  experimental, and the **view toggle** for whichever of Sheet / Tab / Piano-roll
  the stem actually produced (same availability logic as today's `StemPanel`;
  piano roll is kept even though the mock only drew Tab/Sheet).
- The active interactive viewer (`SheetMusic` / `Tab` / `PianoRoll`), reused
  unchanged, threaded the shared `audioRef`, `speed`, `loop`, and playing state.
- **🐢 Slow it down** slider (50–100%), moved in from `StemPanel`, reusing
  `usePlaybackRate`.
- **↻ Loop this part** toggle → sets `audio.loop`.
- **Download** links for every artifact the stem has (sheet PDF, MusicXML, MIDI,
  Tab, Audio) — styled warm; preserves today's download affordances.
- An encouraging **cheer** line (static per-stem copy; neutral fallback).
- Any **warnings** from the stem, preserved.

### 4. Play-along bar (dark)

A warm-dark transport that drives the **same** audio element the viewer uses (no
second player):
- **Play / pause** button → toggles the shared audio element.
- "Play along · {stem}" title + status line.
- **Beat dots** — 4 dots; when `meta.bpm` exists they pulse in 4/4 at the tempo
  while playing; when absent they are hidden (no fake beat).
- **🥁 Metronome** toggle — a Web Audio click on each beat at `meta.bpm`, 4/4;
  disabled/hidden when `meta.bpm` is absent.

Seeking is provided by the notation's existing click-to-seek (OSMD overlay,
alphaTab cursor, piano-roll click). For an **ASCII-tab-only** stem (no notation
cursor, uses the fallback `<audio>`), keep the native `<audio controls>` so the
user can still scrub.

### Shared audio coordination

`PracticeResults` holds the play/pause + loop + speed state and a single
`audioRef`. The challenge: the `<audio>` element lives inside the active viewer
(`PianoRoll` / `SheetMusic` / `Tab`), and is recreated when the view or stem
changes. Each viewer gains one optional prop, an
`onAudio?(el: HTMLAudioElement | null)` callback fired from a ref callback on its
`<audio>`, so the parent always holds a handle to the *current* element to drive
`play()`/`pause()` and read `paused`/`duration`. `speed` (existing prop) and a new
`loop` prop are applied inside each viewer via small effects (the `loop` one mirrors
`usePlaybackRate`), so both survive remounts. Play/pause state is read from the
audio element's `play`/`pause`/`ended` events to stay truthful even when the user
uses native controls (ASCII-tab case).

## Data model changes (backend — small)

- `pipeline/pipeline.py` `run_pipeline`: after `grid` is known, set
  `artifacts["meta"] = {"bpm": round(grid.bpm)}` (only when `grid` is not None).
- `modal_app.py` `process_job`: mirror the same — it detects tempo too; write
  `meta.bpm` into the artifacts it stores.
- `apps/web/lib/types.ts`: extend `Job.artifacts` to
  `{ stems: StemArtifacts[]; meta?: { bpm?: number } }`.

Fail-safe: if tempo detection failed (`grid is None`), `meta` is omitted and the
frontend degrades. Requires a Modal redeploy for new jobs to carry `meta.bpm`;
existing/old jobs simply lack it.

## Out of scope (follow-ups)

- Real song **title / artist / key / backend duration** (needs capturing yt-dlp /
  filename metadata + surfacing the detected key). Hero stays generic until then.
- Re-theming the rest of the app (home page, cost page, header) to warm.

## Testing / verification

- `cd apps/web && npx tsc --noEmit && npx next build`.
- Playwright (per the project's UI-testing workflow) against `next dev`, mocking the
  job API:
  - done job **with** `artifacts.meta.bpm` → hero shows BPM chip; metronome +
    beat dots present; toggling metronome works; chip switching swaps the card;
    loop sets `audio.loop`; speed sets `playbackRate`.
  - done job **without** `meta.bpm` → no BPM chip, no metronome/beat dots, no
    errors.
  - Screenshot each state and read it back.

## Files touched

- New: `apps/web/components/PracticeResults.tsx`.
- Edit: `apps/web/components/JobView.tsx` (render `PracticeResults` in the `done`
  branch), `apps/web/lib/types.ts`, `apps/web/app/globals.css` (warm `.bt-*`
  classes for hero/chips/card/play-along), the three player components
  (forward audio ref / `onAudio` + `loop`), `pipeline/pipeline.py`,
  `modal_app.py`.
- Remove: `apps/web/components/StemPanel.tsx` (superseded) once unreferenced.
