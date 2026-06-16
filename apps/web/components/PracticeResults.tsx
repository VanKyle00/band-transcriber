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
    setPlaying(!el.paused); // sync to the active element (it changes on view/stem switch)
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
    // setInterval isn't sample-accurate, so the click can drift a few ms over a long
    // session — fine for a practice-buddy metronome; an AudioWorklet clock would be the
    // production fix if tighter sync is ever needed.
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
  const durLabel = fmtTime(duration); // "" until known (or if the audio length is unknown/∞)
  const setAudio = (el: HTMLAudioElement | null) => setAudioEl(el);
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
          {durLabel ? <span className="bt-meta">{durLabel}</span> : null}
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
                style={{ ["--beat" as string]: `${(60 / bpm) * 4}s`, animationDelay: `-${(i * 60) / bpm}s` }}
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
