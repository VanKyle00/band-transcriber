"use client";

import { useEffect, useRef, useState } from "react";

import { usePlaybackRate } from "@/lib/usePlaybackRate";

// A readable, self-contained piano roll: pitch-labelled axis on the left, notes on a
// time x pitch grid that zooms (horizontally) and pans (horizontal scroll), with a
// playhead synced to the stem's separated audio. Replaces html-midi-player, whose
// fixed visualizer had no labels, zoom, or pan.

type Note = { midi: number; name: string; time: number; duration: number };

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteName = (midi: number) => `${NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`;
const isBlackKey = (midi: number) => [1, 3, 6, 8, 10].includes(midi % 12);

// Drums aren't pitched: each GM percussion note is a kit piece. Label rows by piece.
const DRUM_LABELS: Record<number, string> = { 36: "Kick", 38: "Snare", 42: "Hi-hat" };

const ROW = 12; // px per semitone

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
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [duration, setDuration] = useState(1);
  const [pxPerSec, setPxPerSec] = useState(90);
  const [tip, setTip] = useState<string | null>(null);
  const [playT, setPlayT] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);
  usePlaybackRate(audio, speed);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { Midi } = await import("@tonejs/midi");
      const buf = await (await fetch(url)).arrayBuffer();
      if (cancelled) return;
      const midi = new Midi(buf);
      const ns: Note[] = [];
      for (const t of midi.tracks)
        for (const n of t.notes)
          ns.push({ midi: n.midi, name: n.name, time: n.time, duration: n.duration });
      ns.sort((a, b) => a.time - b.time);
      setNotes(ns);
      setDuration(Math.max(midi.duration, ...ns.map((n) => n.time + n.duration), 1));
    })().catch(() => setNotes([]));
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (!notes) return <p className="muted">Loading piano roll…</p>;
  if (notes.length === 0) return <p className="muted">No notes detected in this stem.</p>;

  const minMidi = Math.min(...notes.map((n) => n.midi)) - 1;
  const maxMidi = Math.max(...notes.map((n) => n.midi)) + 1;
  const rows = maxMidi - minMidi + 1;
  const height = rows * ROW;
  const width = Math.max(duration * pxPerSec, 240);
  const yOf = (midi: number) => (maxMidi - midi) * ROW;
  const isDrums = id === "drums";

  function seek(e: React.MouseEvent<SVGSVGElement>) {
    if (!audio.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    audio.current.currentTime = Math.max(0, (e.clientX - rect.left) / pxPerSec);
  }

  return (
    <div className="pianoroll">
      <div className="pr-controls">
        <button type="button" aria-label="Zoom out" onClick={() => setPxPerSec((p) => Math.max(20, p / 1.5))}>
          −
        </button>
        <button type="button" aria-label="Zoom in" onClick={() => setPxPerSec((p) => Math.min(700, p * 1.5))}>
          +
        </button>
        <span className="muted">zoom · drag the scrollbar to pan{audioUrl ? " · click to seek" : ""}</span>
        {tip && <span className="pr-tip">{tip}</span>}
      </div>

      <div className="pr-body" style={{ height }}>
        <div className="pr-axis">
          {Array.from({ length: rows }, (_, i) => {
            const m = maxMidi - i;
            const label = isDrums ? DRUM_LABELS[m] : m % 12 === 0 ? noteName(m) : undefined;
            return (
              <div key={m} className={`pr-axis-row${!isDrums && isBlackKey(m) ? " black" : ""}`} style={{ height: ROW }}>
                {label && <span>{label}</span>}
              </div>
            );
          })}
        </div>

        <div className="pr-scroll">
          <svg
            width={width}
            height={height}
            onClick={audioUrl ? seek : undefined}
            onMouseLeave={() => setTip(null)}
            style={{ cursor: audioUrl ? "text" : "default", display: "block" }}
          >
            {Array.from({ length: rows }, (_, i) => {
              const m = maxMidi - i;
              return (
                <rect key={m} x={0} y={i * ROW} width={width} height={ROW} className={`pr-bg${isBlackKey(m) ? " black" : ""}`} />
              );
            })}
            {Array.from({ length: rows }, (_, i) => maxMidi - i)
              .filter((m) => m % 12 === 0)
              .map((m) => (
                <line key={m} x1={0} x2={width} y1={yOf(m) + ROW} y2={yOf(m) + ROW} className="pr-grid" />
              ))}
            {notes.map((n, i) => (
              <rect
                key={i}
                x={n.time * pxPerSec}
                y={yOf(n.midi) + 0.5}
                width={Math.max(n.duration * pxPerSec, 2)}
                height={ROW - 1}
                rx={2}
                className="pr-note"
                onMouseEnter={() => setTip(`${n.name} · ${n.time.toFixed(2)}s`)}
              />
            ))}
            {audioUrl && <line className="pr-playhead" x1={playT * pxPerSec} x2={playT * pxPerSec} y1={0} y2={height} />}
          </svg>
        </div>
      </div>

      {audioUrl && (
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
      )}
    </div>
  );
}
