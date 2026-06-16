"use client";

import { useRef, useState } from "react";

import type { StemArtifacts } from "@/lib/types";
import { usePlaybackRate } from "@/lib/usePlaybackRate";
import PianoRoll from "./PianoRoll";
import SheetMusic from "./SheetMusic";
import Tab from "./Tab";

type View = "sheet" | "tab" | "roll";

export default function StemPanel({ stem }: { stem: StemArtifacts }) {
  // Default to whatever this stem actually produced.
  const available: View[] = [
    stem.musicxml ? ("sheet" as const) : null,
    stem.tab || stem.tab_alphatex ? ("tab" as const) : null,
    stem.midi ? ("roll" as const) : null,
  ].filter(Boolean) as View[];

  const [view, setView] = useState<View>(available[0] ?? "roll");
  // "Slow it down": 1 = full speed, down to 0.5 = half. Threaded into each player so
  // the slider controls whichever view is showing; pitch is preserved (see hook).
  const [speed, setSpeed] = useState(1);
  const fallbackAudio = useRef<HTMLAudioElement>(null);
  usePlaybackRate(fallbackAudio, speed);

  return (
    <section className="card">
      <div className="stem-head">
        <h2 style={{ margin: 0, textTransform: "capitalize" }}>
          {stem.name}
          {stem.experimental && <span className="badge">experimental</span>}
        </h2>
        <div className="downloads">
          {stem.sheet_pdf && <a href={stem.sheet_pdf}>PDF</a>}
          {stem.musicxml && <a href={stem.musicxml}>MusicXML</a>}
          {stem.midi && <a href={stem.midi}>MIDI</a>}
          {stem.tab && <a href={stem.tab}>Tab</a>}
          {stem.audio && <a href={stem.audio}>Audio</a>}
        </div>
      </div>

      {available.length > 0 && (
        <div className="tabs" style={{ marginTop: 14 }}>
          {available.includes("sheet") && (
            <button className={view === "sheet" ? "active" : ""} onClick={() => setView("sheet")}>
              Sheet music
            </button>
          )}
          {available.includes("tab") && (
            <button className={view === "tab" ? "active" : ""} onClick={() => setView("tab")}>
              Tab
            </button>
          )}
          {available.includes("roll") && (
            <button className={view === "roll" ? "active" : ""} onClick={() => setView("roll")}>
              Piano roll
            </button>
          )}
        </div>
      )}

      {view === "sheet" && stem.musicxml && (
        <SheetMusic url={stem.musicxml} audioUrl={stem.audio} speed={speed} />
      )}
      {view === "tab" && (stem.tab || stem.tab_alphatex) && (
        <Tab url={stem.tab} alphatexUrl={stem.tab_alphatex} audioUrl={stem.audio} speed={speed} />
      )}
      {view === "roll" && stem.midi && (
        <PianoRoll url={stem.midi} audioUrl={stem.audio} id={stem.name} speed={speed} />
      )}

      {/* Piano roll, the interactive sheet, and the alphaTab tab each carry their own
          player; show the plain stem audio only for views without one (e.g. ASCII tab). */}
      {!(view === "roll" || (view === "sheet" && stem.musicxml) || (view === "tab" && stem.tab_alphatex)) &&
        stem.audio && (
        <audio ref={fallbackAudio} controls src={stem.audio} style={{ width: "100%", marginTop: 14 }} />
      )}

      {stem.audio && (
        <div className="bt-speed">
          <div className="bt-speed-head">
            <span className="bt-speed-label">🐢 Slow it down</span>
            <span className="bt-speed-val">{Math.round(speed * 100)}% speed</span>
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
      )}

      {stem.warnings?.length > 0 && (
        <p className="muted" style={{ fontSize: 13 }}>
          Notes: {stem.warnings.join("; ")}
        </p>
      )}
    </section>
  );
}
