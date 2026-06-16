"use client";

import { useEffect, useRef } from "react";

import { usePlaybackRate } from "@/lib/usePlaybackRate";

type Slice = { time: number; x: number; y: number; w: number; h: number };

// Renders a MusicXML score with OpenSheetMusicDisplay. With an audio URL it becomes
// interactive: a highlight follows playback and clicking the score seeks the audio there.
// We walk OSMD's cursor once to capture each note-slice's time (from its score timestamp +
// tempo) and on-screen rect (from the note's own SVG element — independent of OSMD's
// shared, collision-prone cursor element), then drive our own overlay box.
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
  const host = useRef<HTMLDivElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  usePlaybackRate(audio, speed);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let osmd: any = null;
    const cleanup: Array<() => void> = [];

    (async () => {
      const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
      const xml = await fetch(url).then((r) => r.text());
      if (cancelled || !host.current) return;
      osmd = new OpenSheetMusicDisplay(host.current, {
        autoResize: false, // our overlay lives inside host; an autoResize re-render would wipe it
        drawingParameters: "compact",
        cursorsOptions: [{ type: 0, color: "#34d082", alpha: 0.4, follow: false }],
      });
      await osmd.load(xml);
      if (cancelled || !host.current) return;
      osmd.render();

      const audioEl = audio.current;
      if (!audioEl) return; // no audio -> static score

      try {
        const bpm = osmd.Sheet?.DefaultStartTempoInBpm || 120;
        const secPerWhole = (4 * 60) / bpm; // 1 whole note = 4 beats
        osmd.enableOrDisableCursors(true);
        const cursor = osmd.cursor;
        if (!cursor) return;
        cursor.reset();

        // Walk the score collecting each note-slice's time + SVG element WITHOUT reading
        // layout (so the cursor walk doesn't force a reflow per note); batch-read rects after.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const raw: { time: number; el: any }[] = [];
        let guard = 0;
        while (!cursor.iterator.EndReached && guard++ < 12000) {
          const ts = cursor.iterator.currentTimeStamp.RealValue as number;
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          let gnotes: any[] = [];
          try { gnotes = cursor.GNotesUnderCursor() || []; } catch { gnotes = []; }
          let el = null;
          for (const g of gnotes) { const e = g.getSVGGElement?.(); if (e) { el = e; break; } }
          if (el) raw.push({ time: ts * secPerWhole, el });
          cursor.next();
        }
        cursor.hide();
        if (raw.length === 0) return;

        const hostRect = host.current.getBoundingClientRect();
        const sx = host.current.scrollLeft, sy = host.current.scrollTop;
        const steps: Slice[] = raw.map(({ time, el }) => {
          const r = el.getBoundingClientRect();
          return {
            time,
            x: r.left - hostRect.left + sx,
            y: r.top - hostRect.top + sy,
            w: Math.max(r.width, 8),
            h: Math.max(r.height, 16),
          };
        });

        const hostEl = host.current;
        hostEl.style.position = "relative";
        const cur = document.createElement("div");
        cur.className = "osmd-cursor";
        cur.style.display = "none";
        hostEl.appendChild(cur);
        cleanup.push(() => cur.remove());

        const place = (i: number) => {
          const s = steps[Math.max(0, Math.min(steps.length - 1, i))];
          cur.style.left = `${s.x - 4}px`;
          cur.style.top = `${s.y - 4}px`;
          cur.style.width = `${s.w + 8}px`;
          cur.style.height = `${s.h + 8}px`;
          cur.style.display = "block";
          // Keep the highlight inside the scroll window as playback advances.
          if (s.y < hostEl.scrollTop + 16 || s.y + s.h > hostEl.scrollTop + hostEl.clientHeight - 16) {
            hostEl.scrollTop = Math.max(0, s.y - hostEl.clientHeight / 3);
          }
        };
        const findByTime = (t: number) => {
          let lo = 0, hi = steps.length - 1, f = 0;
          while (lo <= hi) {
            const m = (lo + hi) >> 1;
            if (steps[m].time <= t + 1e-3) { f = m; lo = m + 1; } else hi = m - 1;
          }
          return f;
        };
        place(0);

        const onTime = () => place(findByTime(audioEl.currentTime));
        const onClick = (e: MouseEvent) => {
          if (!host.current) return;
          const r = host.current.getBoundingClientRect();
          const cx = e.clientX - r.left + host.current.scrollLeft;
          const cy = e.clientY - r.top + host.current.scrollTop;
          let best = 0, bd = Infinity;
          for (let i = 0; i < steps.length; i++) {
            const dx = steps[i].x - cx, dy = steps[i].y - cy;
            const d = dx * dx + dy * dy;
            if (d < bd) { bd = d; best = i; }
          }
          audioEl.currentTime = steps[best].time;
          place(best);
        };

        audioEl.addEventListener("timeupdate", onTime);
        host.current.addEventListener("click", onClick);
        host.current.style.cursor = "pointer";
        cleanup.push(() => audioEl.removeEventListener("timeupdate", onTime));
        cleanup.push(() => host.current?.removeEventListener("click", onClick));
      } catch (e) {
        console.warn("[osmd] cursor sync failed", e);
      }
    })().catch((e) => console.error("OSMD render failed", e));

    return () => {
      cancelled = true;
      cleanup.forEach((f) => f());
      osmd?.clear?.();
    };
  }, [url, audioUrl]);

  return (
    <div>
      <div className="osmd" ref={host} />
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
    </div>
  );
}
