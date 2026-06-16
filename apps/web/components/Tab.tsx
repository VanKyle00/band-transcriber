"use client";

import { useEffect, useRef, useState } from "react";

import { usePlaybackRate } from "@/lib/usePlaybackRate";

// Tab renders two ways:
//  - if an AlphaTex artifact exists, alphaTab engraves an interactive staff + tab
//  - otherwise we fall back to the server-generated ASCII tab in a <pre>
export default function Tab({
  url,
  alphatexUrl,
  audioUrl,
  speed = 1,
}: {
  url?: string;
  alphatexUrl?: string;
  audioUrl?: string;
  speed?: number;
}) {
  if (alphatexUrl) return <AlphaTexTab url={alphatexUrl} audioUrl={audioUrl} speed={speed} />;
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

const CDN = "https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.8.3/dist";

// Load alphaTab from the CDN as a plain script (cached on window). Importing the npm
// module instead makes the bundler mis-resolve alphaTab's audio worklet to a file:// path,
// so the player never initializes. Loaded from the CDN, alphaTab resolves its own assets.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function loadAlphaTab(): Promise<any> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any;
  if (w.alphaTab) return Promise.resolve(w.alphaTab);
  if (!w.__atLoad) {
    w.__atLoad = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `${CDN}/alphaTab.js`;
      s.async = true;
      s.onload = () => resolve(w.alphaTab);
      s.onerror = () => reject(new Error("alphaTab failed to load"));
      document.head.appendChild(s);
    });
  }
  return w.__atLoad;
}

// alphaTab is a browser-only library; load it in the effect so it never runs during SSR.
// We enable alphaTab's player only for its beat cursor, keep it muted, and drive the cursor
// from the SEPARATED STEM audio (the real recording) — so what you hear matches the cursor.
// Clicking a note moves alphaTab's cursor to that beat; we seek the stem audio to match.
function AlphaTexTab({ url, audioUrl, speed = 1 }: { url: string; audioUrl?: string; speed?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const apiRef = useRef<any>(null);
  const readyRef = useRef(false);
  const endRef = useRef(0); // alphaTab's total song time (ms), to scale tab<->audio time
  const [error, setError] = useState<string | null>(null);
  usePlaybackRate(audioRef, speed);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let api: any;

    (async () => {
      try {
        const tex = await (await fetch(url)).text();
        if (cancelled || !ref.current) return;
        const alphaTab = await loadAlphaTab();
        if (cancelled || !ref.current || !alphaTab) return;
        api = new alphaTab.AlphaTabApi(ref.current, {
          core: { fontDirectory: `${CDN}/font/` },
          // Page layout wraps bars into stacked lines (no endless horizontal scroll).
          display: { layoutMode: "page" },
          player: {
            enablePlayer: true,
            enableCursor: true,
            enableUserInteraction: true, // click a beat to move the cursor there
            soundFont: `${CDN}/soundfont/sonivox.sf2`,
            scrollElement: ref.current, // follow the cursor within our scroll window
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } as any);
        apiRef.current = api;
        api.error?.on((e: unknown) => console.warn("[alphaTab]", String(e)));
        api.playerReady.on(() => { readyRef.current = true; api.masterVolume = 0; });
        api.playerPositionChanged?.on((e: { endTime?: number }) => {
          if (e?.endTime && e.endTime > 0) endRef.current = e.endTime;
        });
        // Clicking a note moves alphaTab's player to that beat (a tick after the event), so
        // we read its tab time on the next frame and seek the stem audio to the matching spot.
        api.beatMouseDown?.on(() => {
          const a = audioRef.current;
          if (!a) return;
          window.setTimeout(() => {
            const tp = api.timePosition || 0, end = endRef.current, dur = a.duration;
            a.currentTime = end > 0 && dur > 0 && isFinite(dur) ? (tp / end) * dur : tp / 1000;
          }, 40);
        });
        api.tex(tex);
      } catch {
        if (!cancelled) setError("Failed to render tab.");
      }
    })();

    return () => {
      cancelled = true;
      api?.destroy();
      apiRef.current = null;
      readyRef.current = false;
    };
  }, [url]);

  const onTime = () => {
    const api = apiRef.current;
    const a = audioRef.current;
    if (!(api && a && readyRef.current)) return;
    const end = endRef.current, dur = a.duration;
    // Scale audio time -> tab time by the duration ratio so the cursor tracks even when the
    // tab's (default) tempo differs from the recording; fall back to 1:1 until end is known.
    api.timePosition = end > 0 && dur > 0 && isFinite(dur) ? (a.currentTime / dur) * end : a.currentTime * 1000;
  };

  if (error) return <pre className="tab">{error}</pre>;
  return (
    <div>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 8px" }}>
        Cursor follows the stem audio · click a note to jump there.
      </p>
      <div className="alphatab" ref={ref} />
      {audioUrl && (
        <audio ref={audioRef} controls src={audioUrl} style={{ width: "100%", marginTop: 10 }} onTimeUpdate={onTime} />
      )}
    </div>
  );
}
