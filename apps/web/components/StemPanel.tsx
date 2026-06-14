"use client";

import { useState } from "react";

import type { StemArtifacts } from "@/lib/types";
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

      {view === "sheet" && stem.musicxml && <SheetMusic url={stem.musicxml} />}
      {view === "tab" && (stem.tab || stem.tab_alphatex) && (
        <Tab url={stem.tab} alphatexUrl={stem.tab_alphatex} />
      )}
      {view === "roll" && stem.midi && (
        <PianoRoll url={stem.midi} audioUrl={stem.audio} id={stem.name} />
      )}

      {/* The piano roll carries its own synced player; show the plain one elsewhere. */}
      {view !== "roll" && stem.audio && (
        <audio controls src={stem.audio} style={{ width: "100%", marginTop: 14 }} />
      )}

      {stem.warnings?.length > 0 && (
        <p className="muted" style={{ fontSize: 13 }}>
          Notes: {stem.warnings.join("; ")}
        </p>
      )}
    </section>
  );
}
