# Warm Practice Buddy Results Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dark stacked-stem results view with the warm "Practice Buddy" layout (hero, instrument chips, a focused practice card per stem, play-along bar), reusing the existing interactive players, plus storing the detected BPM so the BPM chip + metronome are real.

**Architecture:** A new `PracticeResults` client component owns the selected-stem + transport state and renders the four warm sections; the existing `SheetMusic`/`Tab`/`PianoRoll` viewers are reused unchanged except for one new `onAudio` callback that hands the parent the current `<audio>` element to drive play/pause/loop/duration. The pipeline writes `round(grid.bpm)` into `artifacts.meta.bpm`; the frontend degrades gracefully when it is absent.

**Tech Stack:** Next.js 15 / React 19 / TypeScript (web), Python + pytest (pipeline), Web Audio API (metronome). No web unit-test runner exists, so web tasks verify with `npx tsc --noEmit`, `npx next build`, and Playwright screenshots (per `docs`/memory UI-testing workflow). The pipeline uses pytest (real TDD).

**Deploy note:** Vercel auto-deploys the frontend on push to `main`. The backend BPM change only takes effect after a **Modal redeploy** (`modal deploy modal_app.py`), which the user runs. Until then `meta.bpm` is absent and the UI degrades — so the frontend is safe to ship first.

---

## File Structure

- **Modify** `pipeline/postprocess.py` — add pure `build_meta(bpm)` helper.
- **Modify** `pipeline/pipeline.py:143` — attach `meta` to the artifacts manifest.
- **Modify** `modal_app.py:180` — same, using the detected tempo.
- **Modify** `pipeline/tests/test_postprocess.py` — tests for `build_meta`.
- **Modify** `apps/web/lib/types.ts` — extend `Job.artifacts` with `meta`.
- **Modify** `apps/web/components/PianoRoll.tsx`, `SheetMusic.tsx`, `Tab.tsx` — add `onAudio?` callback.
- **Modify** `apps/web/app/globals.css` — warm `.bt-*` classes for hero/chips/card/play-along.
- **Create** `apps/web/components/PracticeResults.tsx` — the new results view.
- **Modify** `apps/web/components/JobView.tsx` — render `PracticeResults` in the `done` branch.
- **Remove** `apps/web/components/StemPanel.tsx` — superseded (its speed slider + views move into the practice card).

---

## Task 1: Backend — store detected BPM in `artifacts.meta`

**Files:**
- Modify: `pipeline/postprocess.py` (add helper near the top-level functions)
- Modify: `pipeline/pipeline.py:143`
- Modify: `modal_app.py:180`
- Test: `pipeline/tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_postprocess.py` (extend the existing import on line 9 to include `build_meta`):

```python
# change line 9 to:
from pipeline.postprocess import Grid, Note, _fold_tempo, build_meta, quantize_and_clean


def test_build_meta_rounds_bpm():
    assert build_meta(96.4) == {"bpm": 96}


def test_build_meta_rounds_bpm_up():
    assert build_meta(119.6) == {"bpm": 120}


def test_build_meta_none_is_empty():
    assert build_meta(None) == {}


def test_build_meta_nonpositive_is_empty():
    assert build_meta(0.0) == {}


def test_build_meta_nan_is_empty():
    assert build_meta(float("nan")) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Administrator/band-transcriber && python -m pytest pipeline/tests/test_postprocess.py -q`
Expected: FAIL with `ImportError: cannot import name 'build_meta'`.

- [ ] **Step 3: Add the helper**

In `pipeline/postprocess.py`, add this top-level function (place it right after the `detect_tempo` function, ~line 106):

```python
def build_meta(bpm: float | None) -> dict:
    """Job-level metadata for the artifacts manifest. Empty when tempo is unknown."""
    if bpm is None or not math.isfinite(bpm) or bpm <= 0:
        return {}
    return {"bpm": round(bpm)}
```

(`math` is already imported at the top of `postprocess.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/Administrator/band-transcriber && python -m pytest pipeline/tests/test_postprocess.py -q`
Expected: PASS (all `build_meta` tests green, existing tests still green).

- [ ] **Step 5: Wire into `run_pipeline`**

In `pipeline/pipeline.py`, replace line 143 (`artifacts = {"stems": results}`) with:

```python
        artifacts = {"stems": results}
        meta = postprocess.build_meta(grid.bpm if grid is not None else None)
        if meta:
            artifacts["meta"] = meta
```

(`postprocess` is already imported in `pipeline.py`.)

- [ ] **Step 6: Wire into Modal `process_job`**

In `modal_app.py`, replace line 180 (`artifacts = {"stems": results}`) with:

```python
        artifacts = {"stems": results}
        meta = postprocess.build_meta(grid_tuple[0] if grid_tuple is not None else None)
        if meta:
            artifacts["meta"] = meta
```

(`postprocess` is already imported inside `process_job` on line 147: `from pipeline import download, postprocess, storage`.)

- [ ] **Step 7: Run the full pipeline test suite**

Run: `cd C:/Users/Administrator/band-transcriber && python -m pytest pipeline/tests -q`
Expected: PASS (previously 43 passed, 3 skipped → now 48 passed, 3 skipped).

- [ ] **Step 8: Commit**

```bash
git add pipeline/postprocess.py pipeline/pipeline.py modal_app.py pipeline/tests/test_postprocess.py
git commit -m "feat(pipeline): surface detected BPM in artifacts.meta for the results UI"
```

---

## Task 2: Frontend types — extend `Job.artifacts` with `meta`

**Files:**
- Modify: `apps/web/lib/types.ts:18-23`

- [ ] **Step 1: Edit the `Job` type**

In `apps/web/lib/types.ts`, change the `artifacts` field of `Job` (line 19) from:

```ts
  artifacts?: { stems: StemArtifacts[] };
```

to:

```ts
  artifacts?: { stems: StemArtifacts[]; meta?: { bpm?: number } };
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: exit 0 (no errors).

- [ ] **Step 3: Commit**

```bash
git add apps/web/lib/types.ts
git commit -m "feat(web): add artifacts.meta.bpm to the Job type"
```

---

## Task 3: Players — add an `onAudio` callback prop

Each viewer keeps its internal audio ref (used for cursor/seek logic) but also notifies the parent of the current `<audio>` element via a ref callback, so `PracticeResults` can drive play/pause/loop and read duration. `speed` is already wired (shipped in `66e0f23`).

**Files:**
- Modify: `apps/web/components/PianoRoll.tsx`
- Modify: `apps/web/components/SheetMusic.tsx`
- Modify: `apps/web/components/Tab.tsx`

- [ ] **Step 1: PianoRoll — add the prop + callback ref**

In `apps/web/components/PianoRoll.tsx`, extend the props (the block starting `}: {` after `speed = 1,`) to add `onAudio`:

```tsx
export default function PianoRoll({
  url,
  audioUrl,
  id,
  speed = 1,
  onAudio,
}: {
  url: string;
  audioUrl?: string;
  id: string;
  speed?: number;
  onAudio?: (el: HTMLAudioElement | null) => void;
}) {
```

Then change the audio element near the end from `<audio ref={audio} ...>` to use a callback ref that sets both:

```tsx
        <audio
          ref={(el) => {
            audio.current = el;
            onAudio?.(el);
          }}
          controls
          src={audioUrl}
          style={{ width: "100%", marginTop: 10 }}
          onTimeUpdate={(e) => setPlayT(e.currentTarget.currentTime)}
        />
```

- [ ] **Step 2: SheetMusic — add the prop + callback ref**

In `apps/web/components/SheetMusic.tsx`, extend the props to add `onAudio`:

```tsx
export default function SheetMusic({
  url,
  audioUrl,
  speed = 1,
  onAudio,
}: {
  url: string;
  audioUrl?: string;
  speed?: number;
  onAudio?: (el: HTMLAudioElement | null) => void;
}) {
```

Then change the audio element at the bottom:

```tsx
      {audioUrl && (
        <audio
          ref={(el) => {
            audio.current = el;
            onAudio?.(el);
          }}
          controls
          src={audioUrl}
          style={{ width: "100%", marginTop: 10 }}
        />
      )}
```

- [ ] **Step 3: Tab — thread the prop through to AlphaTexTab**

In `apps/web/components/Tab.tsx`, extend the wrapper `Tab` props + forward `onAudio` to `AlphaTexTab`:

```tsx
export default function Tab({
  url,
  alphatexUrl,
  audioUrl,
  speed = 1,
  onAudio,
}: {
  url?: string;
  alphatexUrl?: string;
  audioUrl?: string;
  speed?: number;
  onAudio?: (el: HTMLAudioElement | null) => void;
}) {
  if (alphatexUrl) return <AlphaTexTab url={alphatexUrl} audioUrl={audioUrl} speed={speed} onAudio={onAudio} />;
  if (url) return <AsciiTab url={url} />;
  return null;
}
```

Update the `AlphaTexTab` signature to accept `onAudio`:

```tsx
function AlphaTexTab({ url, audioUrl, speed = 1, onAudio }: { url: string; audioUrl?: string; speed?: number; onAudio?: (el: HTMLAudioElement | null) => void }) {
```

And its audio element at the bottom:

```tsx
      {audioUrl && (
        <audio
          ref={(el) => {
            audioRef.current = el;
            onAudio?.(el);
          }}
          controls
          src={audioUrl}
          style={{ width: "100%", marginTop: 10 }}
          onTimeUpdate={onTime}
        />
      )}
```

- [ ] **Step 4: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/PianoRoll.tsx apps/web/components/SheetMusic.tsx apps/web/components/Tab.tsx
git commit -m "feat(web): expose current audio element from players via onAudio callback"
```

---

## Task 4: Warm CSS for the results page

**Files:**
- Modify: `apps/web/app/globals.css` (append after the existing `.bt-speed-ends` block)

- [ ] **Step 1: Append the warm results styles**

Add to the end of `apps/web/app/globals.css`:

```css
/* --- Warm results page (Practice Buddy) --- */
@keyframes bt-beat { 0%, 100% { opacity: .35; transform: scale(1); } 30% { opacity: 1; transform: scale(1.45); } }

.bt-res { font-family: var(--font-nunito), system-ui, sans-serif; color: #2A2018; }

/* hero */
.bt-hero {
  position: relative; overflow: hidden; border-radius: 26px 26px 0 0;
  padding: 30px 32px; background: linear-gradient(135deg, #FBE3CC, #FBD7BE);
}
.bt-hero-decor { position: absolute; border-radius: 50%; pointer-events: none; }
.bt-hero-blob1 { width: 120px; height: 120px; background: #F6C49B; opacity: .55; top: -30px; right: 40px; animation: bt-floaty 6s ease-in-out infinite; }
.bt-hero-blob2 { width: 60px; height: 60px; background: #EE9F6E; opacity: .5; bottom: -14px; right: 170px; animation: bt-floaty 5s ease-in-out infinite .8s; }
.bt-hero-row { position: relative; display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
.bt-hero-mascot { width: 74px; height: 74px; border-radius: 22px; background: #E8743B; display: flex; align-items: center; justify-content: center; font-size: 36px; flex-shrink: 0; animation: bt-bob 4s ease-in-out infinite; box-shadow: 0 12px 24px -8px #C85A3E; }
.bt-hero-eyebrow { font-size: 11px; font-weight: 800; letter-spacing: 0.14em; color: #B5602F; margin-bottom: 6px; }
.bt-hero-title { font-family: var(--font-bricolage), system-ui, sans-serif; font-weight: 800; font-size: 30px; margin: 0; line-height: 1.05; letter-spacing: -0.02em; color: #3a2113; }
.bt-hero-chips { position: relative; display: flex; flex-wrap: wrap; gap: 8px; }
.bt-meta { display: inline-flex; align-items: center; gap: 6px; background: #FFF6EC; border-radius: 999px; padding: 6px 13px; font-size: 13px; font-weight: 800; color: #7a5b3a; }

/* body wrapper continues the card paper under the hero */
.bt-pick { background: #FDF1E2; padding: 26px 32px 0; font-size: 13px; font-weight: 800; color: #A8704A; }
.bt-chips { background: #FDF1E2; padding: 12px 32px 24px; display: flex; flex-wrap: wrap; gap: 10px; }
.bt-chip { display: inline-flex; align-items: center; gap: 8px; padding: 11px 17px; border-radius: 14px; font-size: 14.5px; font-weight: 800; cursor: pointer; font-family: var(--font-nunito), system-ui, sans-serif; transition: all .18s ease; border: 1.5px solid #EDDFCD; background: #FFFBF5; color: #5b4a3a; }
.bt-chip.on { color: #fff; }
.bt-chip-dot { width: 11px; height: 11px; border-radius: 4px; display: inline-block; }

/* practice card */
.bt-card { background: #FFFBF5; border: 1.5px solid #EDDFCD; border-radius: 22px; padding: 24px; margin: 0 32px; box-shadow: 0 12px 28px -18px rgba(80, 50, 20, .4); }
.bt-card-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 18px; }
.bt-card-id { display: flex; align-items: center; gap: 11px; }
.bt-card-bigdot { width: 16px; height: 16px; border-radius: 5px; display: inline-block; }
.bt-card-name { font-family: var(--font-bricolage), system-ui, sans-serif; font-weight: 800; font-size: 22px; }
.bt-card-note { font-size: 13px; color: #9a8b76; font-weight: 600; }
.bt-seg { display: flex; background: #F1E4D2; border-radius: 11px; padding: 3px; }
.bt-seg-btn { padding: 8px 14px; border-radius: 9px; border: none; cursor: pointer; font-size: 13.5px; font-weight: 800; font-family: var(--font-nunito), system-ui, sans-serif; background: transparent; color: #9a8b76; }
.bt-seg-btn.on { background: #fff; color: #2A2018; box-shadow: 0 2px 6px -2px rgba(0, 0, 0, .2); }
.bt-viewer { margin-bottom: 4px; }
.bt-card-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 16px; }
.bt-loop { background: #F4E7D6; color: #7a5b3a; border: none; border-radius: 12px; padding: 12px 16px; font-size: 14px; font-weight: 800; cursor: pointer; font-family: var(--font-nunito), system-ui, sans-serif; white-space: nowrap; }
.bt-loop.on { background: #2A2018; color: #FFF3E6; }
.bt-dl { display: flex; gap: 14px; flex-wrap: wrap; margin-left: auto; }
.bt-dl a { font-size: 13px; font-weight: 800; color: #B5602F; }
.bt-cheer { text-align: center; margin-top: 16px; font-size: 13.5px; color: #9a8b76; font-weight: 700; }

/* play-along bar */
.bt-play { margin: 22px 32px 0; background: #2A2018; border-radius: 18px; padding: 14px 18px; display: flex; align-items: center; gap: 16px; font-family: var(--font-nunito), system-ui, sans-serif; }
.bt-play-btn { width: 46px; height: 46px; border-radius: 50%; border: none; cursor: pointer; color: #2A2018; background: #F0A05a; font-size: 15px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-weight: 800; }
.bt-play-btn:disabled { opacity: .5; cursor: not-allowed; }
.bt-play-info { flex: 1; min-width: 0; }
.bt-play-title { color: #FFF3E6; font-weight: 800; font-size: 14.5px; font-family: var(--font-bricolage), system-ui, sans-serif; }
.bt-play-status { color: #b8a18c; font-size: 12.5px; font-weight: 600; }
.bt-beats { display: flex; align-items: center; gap: 8px; }
.bt-beat { width: 8px; height: 8px; border-radius: 50%; background: #5a4a3a; display: inline-block; }
.bt-beat.on { animation: bt-beat var(--beat, .8s) ease-in-out infinite; background: #F0A05a; }
.bt-metro { background: transparent; border: 1.5px solid #5a4a3a; border-radius: 11px; padding: 9px 13px; font-size: 12.5px; font-weight: 800; cursor: pointer; font-family: var(--font-nunito), system-ui, sans-serif; white-space: nowrap; color: #cbb39c; }
.bt-metro.on { background: #E8743B; border-color: #E8743B; color: #fff; }
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/app/globals.css
git commit -m "feat(web): warm CSS for the Practice Buddy results page"
```

---

## Task 5: Build the `PracticeResults` component

**Files:**
- Create: `apps/web/components/PracticeResults.tsx`

- [ ] **Step 1: Create the component**

Create `apps/web/components/PracticeResults.tsx` with exactly:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import type { Job, StemArtifacts } from "@/lib/types";
import { usePlaybackRate } from "@/lib/usePlaybackRate";
import PianoRoll from "./PianoRoll";
import SheetMusic from "./SheetMusic";
import Tab from "./Tab";

type View = "sheet" | "tab" | "roll";

// Friendly per-stem trimmings. Real stems are drums/bass/vocals/guitar/piano;
// anything else falls back to neutral values.
const COLOR: Record<string, string> = {
  vocals: "#E8743B", guitar: "#C77F3C", bass: "#B0573E", drums: "#6E8E55", piano: "#CE9A3A",
};
const NOTE: Record<string, string> = {
  vocals: "lead melody", guitar: "rhythm & riff", bass: "low-end groove",
  drums: "the beat", piano: "chords & pads",
};
const CHEER: Record<string, string> = {
  vocals: "Take a breath and sing it out — you sound great. 💛",
  guitar: "Nice and easy. Loop the tricky bar until it clicks. 🎸",
  bass: "Lock in with the kick drum and you're golden. 🎶",
  drums: "Count it out loud — one and two and. You've got this. 🥁",
  piano: "Left hand keeps time, right hand sings. Have fun! 🎹",
};
const colorOf = (n: string) => COLOR[n] ?? "#9a8b76";
const noteOf = (n: string) => NOTE[n] ?? "this part";
const cheerOf = (n: string) => CHEER[n] ?? "Take it slow and have fun. 🎵";
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function viewsFor(stem: StemArtifacts): View[] {
  return [
    stem.musicxml ? ("sheet" as const) : null,
    stem.tab || stem.tab_alphatex ? ("tab" as const) : null,
    stem.midi ? ("roll" as const) : null,
  ].filter(Boolean) as View[];
}
// True when the active view renders its own <audio> (so we don't add a fallback).
function viewHasOwnAudio(stem: StemArtifacts, view: View): boolean {
  return (
    view === "roll" ||
    (view === "sheet" && !!stem.musicxml) ||
    (view === "tab" && !!stem.tab_alphatex)
  );
}
function fmtTime(s: number): string {
  if (!isFinite(s) || s <= 0) return "";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function PracticeResults({ jobId, job }: { jobId: string; job: Job }) {
  const stems = job.artifacts?.stems ?? [];
  const bpm = job.artifacts?.meta?.bpm;

  const [selected, setSelected] = useState(stems[0]?.name ?? "");
  const stem = stems.find((s) => s.name === selected) ?? stems[0];

  const [view, setView] = useState<View>(() => viewsFor(stems[0] ?? ({} as StemArtifacts))[0] ?? "roll");
  const [speed, setSpeed] = useState(1);
  const [loop, setLoop] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [metro, setMetro] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioEl, setAudioEl] = useState<HTMLAudioElement | null>(null);
  const fallbackAudio = useRef<HTMLAudioElement>(null);
  usePlaybackRate(fallbackAudio, speed);

  // Switching stems: reset the view to that stem's first view and stop playback.
  useEffect(() => {
    if (!stem) return;
    setView(viewsFor(stem)[0] ?? "roll");
    setPlaying(false);
    setDuration(0);
    setAudioEl(null);
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  // Apply loop + read play/pause/duration from whichever audio element is active.
  useEffect(() => {
    const el = audioEl;
    if (!el) return;
    el.loop = loop;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onMeta = () => setDuration(el.duration);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    el.addEventListener("loadedmetadata", onMeta);
    if (el.readyState >= 1) setDuration(el.duration);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
      el.removeEventListener("loadedmetadata", onMeta);
    };
  }, [audioEl, loop]);

  // Metronome: a Web Audio click on each beat at the detected tempo, while playing.
  useEffect(() => {
    if (!metro || !playing || !bpm) return;
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const click = () => {
      const t = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 1000;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.5, t + 0.001);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.06);
    };
    click();
    const id = window.setInterval(click, 60000 / bpm);
    return () => {
      window.clearInterval(id);
      void ctx.close();
    };
  }, [metro, playing, bpm]);

  if (!stem) {
    return (
      <>
        <h1>Your transcription</h1>
        <p className="lede">Job {jobId}</p>
        <div className="card">No stems were produced for this job.</div>
      </>
    );
  }

  const views = viewsFor(stem);
  const ownAudio = viewHasOwnAudio(stem, view);
  const setAudio = (el: HTMLAudioElement | null) => {
    if (el) setAudioEl(el);
  };
  const togglePlay = () => {
    const el = audioEl;
    if (!el) return;
    if (el.paused) void el.play().catch(() => {});
    else el.pause();
  };

  return (
    <div className="bt-res">
      <div className="bt-hero">
        <span className="bt-hero-decor bt-hero-blob1" />
        <span className="bt-hero-decor bt-hero-blob2" />
        <div className="bt-hero-row">
          <div className="bt-hero-mascot">🌼</div>
          <div>
            <div className="bt-hero-eyebrow">LET&apos;S PRACTICE TOGETHER</div>
            <h1 className="bt-hero-title">Let&apos;s learn this track,<br />one part at a time.</h1>
          </div>
        </div>
        <div className="bt-hero-chips">
          {bpm ? <span className="bt-meta">♩ {bpm} BPM</span> : null}
          <span className="bt-meta">{stems.length} {stems.length === 1 ? "part" : "parts"}</span>
          {duration ? <span className="bt-meta">{fmtTime(duration)}</span> : null}
        </div>
      </div>

      <div className="bt-pick">Which part do you want to play today?</div>
      <div className="bt-chips">
        {stems.map((s) => {
          const on = s.name === selected;
          const c = colorOf(s.name);
          return (
            <button
              key={s.name}
              type="button"
              onClick={() => setSelected(s.name)}
              className={`bt-chip${on ? " on" : ""}`}
              style={on ? { background: c, borderColor: c, boxShadow: `0 10px 20px -10px ${c}` } : undefined}
            >
              <span className="bt-chip-dot" style={{ background: on ? "#fff" : c }} />
              {cap(s.name)}
            </button>
          );
        })}
      </div>

      <div className="bt-card">
        <div className="bt-card-head">
          <div className="bt-card-id">
            <span className="bt-card-bigdot" style={{ background: colorOf(stem.name) }} />
            <div>
              <div className="bt-card-name">
                {cap(stem.name)}
                {stem.experimental && <span className="badge">experimental</span>}
              </div>
              <div className="bt-card-note">{noteOf(stem.name)}</div>
            </div>
          </div>
          {views.length > 1 && (
            <div className="bt-seg">
              {views.includes("sheet") && (
                <button type="button" className={`bt-seg-btn${view === "sheet" ? " on" : ""}`} onClick={() => setView("sheet")}>♪ Sheet</button>
              )}
              {views.includes("tab") && (
                <button type="button" className={`bt-seg-btn${view === "tab" ? " on" : ""}`} onClick={() => setView("tab")}>Tab</button>
              )}
              {views.includes("roll") && (
                <button type="button" className={`bt-seg-btn${view === "roll" ? " on" : ""}`} onClick={() => setView("roll")}>Piano roll</button>
              )}
            </div>
          )}
        </div>

        <div className="bt-viewer">
          {view === "sheet" && stem.musicxml && (
            <SheetMusic url={stem.musicxml} audioUrl={stem.audio} speed={speed} onAudio={setAudio} />
          )}
          {view === "tab" && (stem.tab || stem.tab_alphatex) && (
            <Tab url={stem.tab} alphatexUrl={stem.tab_alphatex} audioUrl={stem.audio} speed={speed} onAudio={setAudio} />
          )}
          {view === "roll" && stem.midi && (
            <PianoRoll url={stem.midi} audioUrl={stem.audio} id={stem.name} speed={speed} onAudio={setAudio} />
          )}
          {!ownAudio && stem.audio && (
            <audio
              ref={(el) => {
                fallbackAudio.current = el;
                setAudio(el);
              }}
              controls
              src={stem.audio}
              style={{ width: "100%", marginTop: 14 }}
            />
          )}
        </div>

        <div className="bt-speed">
          <div className="bt-speed-head">
            <span className="bt-speed-label">🐢 Slow it down</span>
            <span className="bt-speed-val">
              {Math.round(speed * 100)}% speed{bpm ? ` · ${Math.round(bpm * speed)} BPM` : ""}
            </span>
          </div>
          <input
            type="range"
            min={50}
            max={100}
            step={5}
            value={Math.round(speed * 100)}
            onChange={(e) => setSpeed(+e.target.value / 100)}
            aria-label="Playback speed"
          />
          <div className="bt-speed-ends">
            <span>Half speed</span>
            <span>Full speed</span>
          </div>
        </div>

        <div className="bt-card-actions">
          <button type="button" className={`bt-loop${loop ? " on" : ""}`} onClick={() => setLoop((v) => !v)}>
            ↻ Loop this part
          </button>
          <div className="bt-dl">
            {stem.sheet_pdf && <a href={stem.sheet_pdf}>PDF</a>}
            {stem.musicxml && <a href={stem.musicxml}>MusicXML</a>}
            {stem.midi && <a href={stem.midi}>MIDI</a>}
            {stem.tab && <a href={stem.tab}>Tab</a>}
            {stem.audio && <a href={stem.audio}>Audio</a>}
          </div>
        </div>

        {stem.warnings?.length > 0 && (
          <p className="muted" style={{ fontSize: 13 }}>Notes: {stem.warnings.join("; ")}</p>
        )}
        <div className="bt-cheer">{cheerOf(stem.name)}</div>
      </div>

      <div className="bt-play">
        <button type="button" className="bt-play-btn" onClick={togglePlay} disabled={!audioEl} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="bt-play-info">
          <div className="bt-play-title">Play along · {cap(stem.name)}</div>
          <div className="bt-play-status">
            {playing
              ? `Playing${bpm ? ` at ${Math.round(bpm * speed)} BPM` : ""}${loop ? " · looping" : ""}${metro ? " · metronome on" : ""}`
              : "Tap play and follow along"}
          </div>
        </div>
        {bpm ? (
          <div className="bt-beats">
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className={`bt-beat${playing ? " on" : ""}`}
                style={{ ["--beat" as string]: `${(60 / bpm) * 4}s`, animationDelay: `${(i * 60) / bpm}s` }}
              />
            ))}
          </div>
        ) : null}
        {bpm ? (
          <button type="button" className={`bt-metro${metro ? " on" : ""}`} onClick={() => setMetro((v) => !v)}>
            🥁 Metronome
          </button>
        ) : null}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: exit 0. (If the `["--beat" as string]` index draws a TS error, change it to `as Record<string, string>` cast on the style object — but `as string` key indexing is accepted by React's CSSProperties in this project's TS config.)

- [ ] **Step 3: Commit**

```bash
git add apps/web/components/PracticeResults.tsx
git commit -m "feat(web): warm Practice Buddy results view (hero, chips, practice card, play-along)"
```

---

## Task 6: Wire `JobView` to `PracticeResults` and remove `StemPanel`

**Files:**
- Modify: `apps/web/components/JobView.tsx`
- Remove: `apps/web/components/StemPanel.tsx`

- [ ] **Step 1: Swap the done branch**

In `apps/web/components/JobView.tsx`, change the import line 6 from:

```tsx
import StemPanel from "./StemPanel";
```

to:

```tsx
import PracticeResults from "./PracticeResults";
```

Then replace the entire `done` branch (the block `if (job?.status === "done") { ... }`) with:

```tsx
  if (job?.status === "done") {
    return <PracticeResults jobId={jobId} job={job} />;
  }
```

- [ ] **Step 2: Delete the superseded component**

```bash
git rm apps/web/components/StemPanel.tsx
```

- [ ] **Step 3: Typecheck + build**

Run: `cd apps/web && npx tsc --noEmit && npx next build`
Expected: exit 0; build succeeds with all routes. (`StemPanel` must have no remaining importers — `grep -r StemPanel apps/web` returns nothing.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/JobView.tsx
git commit -m "feat(web): render PracticeResults for finished jobs; drop StemPanel"
```

---

## Task 7: Visual + behavior verification (Playwright)

No web unit-test runner exists; verify behavior by driving `next dev` with a mocked job API (per the project UI-testing workflow). **Do not run `next build` while `next dev` is running** — restart dev after any build (memory gotcha).

**Files:**
- Create (temporary, deleted at the end): `apps/web/verify-results.cjs`

- [ ] **Step 1: Start the dev server**

Run (background): `cd apps/web && npm run dev`
Note the port from its output (3000, or 3001 if taken).

- [ ] **Step 2: Write the verification script**

Create `apps/web/verify-results.cjs` (set `BASE` to the dev port from Step 1):

```js
const { chromium } = require("playwright");

const BASE = "http://localhost:3001";
const OUT = process.env.TMP_OUT || ".";
const WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";
const TAB = "data:text/plain," + encodeURIComponent("e|--0--2--3--0--|\nB|--1--1--1--1--|");

const stems = [
  { name: "guitar", experimental: true, warnings: [], audio: WAV, tab: TAB },
  { name: "drums", experimental: false, warnings: [], audio: WAV, tab: TAB },
];
const withBpm = { id: "demo", status: "done", stage: "done", artifacts: { stems, meta: { bpm: 96 } } };
const noBpm = { id: "demo", status: "done", stage: "done", artifacts: { stems } };

async function run(job, name, page, OUT) {
  await page.route("**/api/jobs/**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(job) })
  );
  await page.goto(`${BASE}/jobs/demo`, { waitUntil: "networkidle" });
  await page.waitForSelector(".bt-card", { timeout: 8000 });
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  await page.unroute("**/api/jobs/**");
  console.log("saved", name);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 980, height: 1100 } });
  page.on("console", (m) => console.log("[page]", m.type(), m.text()));

  await run(withBpm, "01-results-bpm", page, OUT);
  // switch chip to drums + toggle loop, verify audio.loop
  await page.click(".bt-chips button:nth-child(2)");
  await page.click(".bt-loop");
  const loop = await page.evaluate(() => document.querySelector("audio")?.loop);
  console.log("audio.loop after toggle:", loop);
  // metronome toggle should not throw
  await page.click(".bt-metro");
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/02-results-drums-loop.png`, fullPage: true });

  await run(noBpm, "03-results-nobpm", page, OUT);
  const hasMetro = await page.evaluate(() => !!document.querySelector(".bt-metro"));
  console.log("metronome present without bpm (expect false):", hasMetro);

  await browser.close();
})().catch((e) => { console.error("SCRIPT ERROR", e); process.exit(1); });
```

- [ ] **Step 3: Run the script**

Run: `cd apps/web && mkdir -p /tmp/results-shots && TMP_OUT=/tmp/results-shots node verify-results.cjs`
Expected console:
- `audio.loop after toggle: true`
- `metronome present without bpm (expect false): false`
- three `saved …` lines, no `SCRIPT ERROR`.

- [ ] **Step 4: Read the screenshots**

Read `/tmp/results-shots/01-results-bpm.png`, `02-results-drums-loop.png`, `03-results-nobpm.png` (resolve `/tmp` via `cygpath -w /tmp/results-shots`). Confirm: warm hero with BPM + parts chips; instrument chips with the selected one filled; practice card with the viewer, Slow-it-down slider, loop button, downloads, cheer; dark play-along bar with beat dots + metronome (present only in the BPM screenshots, absent in `03`).

- [ ] **Step 5: Clean up + stop dev**

```bash
rm apps/web/verify-results.cjs
```
Stop the background `next dev` (kill the listener on its port).

- [ ] **Step 6: Final full build (dev stopped)**

Run: `cd apps/web && npx next build`
Expected: exit 0.

---

## Deploy

- [ ] Push to `main` (Vercel auto-deploys the frontend): `git push origin main`
- [ ] **User action:** redeploy Modal so new jobs carry `artifacts.meta.bpm`: `modal deploy modal_app.py`. Until then, finished jobs render without the BPM chip / metronome (graceful).
- [ ] Authoritative check: submit a fresh real job and confirm the warm results page on `https://band-transcriber.vercel.app/jobs/<id>`.

---

## Self-Review

- **Spec coverage:** Hero (Task 5) ✓, instrument chips (Task 5) ✓, practice card with views/speed/loop/downloads/cheer/warnings (Tasks 4-5) ✓, play-along bar + metronome + beat dots (Tasks 4-5) ✓, BPM backend (Task 1) ✓, types (Task 2) ✓, graceful degradation for missing bpm (Task 5 conditionals + Task 7 `03` check) ✓, duration from audio metadata (Task 5) ✓, reuse players via `onAudio` (Task 3) ✓, remove StemPanel (Task 6) ✓.
- **Placeholder scan:** none — all steps carry real code/commands.
- **Type consistency:** `onAudio?: (el: HTMLAudioElement | null) => void` is identical across Task 3 (players) and Task 5 (`setAudio` passed as `onAudio`). `build_meta` signature matches between Task 1 test, helper, and both call sites (`grid.bpm` / `grid_tuple[0]`). `Job.artifacts.meta.bpm` (Task 2) matches `job.artifacts?.meta?.bpm` reads (Task 5).
