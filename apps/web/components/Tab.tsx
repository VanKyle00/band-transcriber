"use client";

import { useEffect, useRef, useState } from "react";

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

// alphaTab is a browser-only library; load it inside the effect so it never runs during
// SSR. We enable its native player (SoundFont synth) so the tab gets a beat cursor that
// follows playback and click-to-seek (enableUserInteraction), with our own play/stop UI.
function AlphaTexTab({ url }: { url: string }) {
  const ref = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const apiRef = useRef<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);

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
            enableUserInteraction: true, // click a beat to seek
            soundFont: `${CDN}/soundfont/sonivox.sf2`,
            scrollElement: ref.current, // follow the cursor within our scroll window
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } as any);
        apiRef.current = api;
        api.error?.on((e: unknown) => console.warn("[alphaTab]", String(e)));
        api.playerReady.on(() => { if (!cancelled) setReady(true); });
        // PlayerState.Playing === 1
        api.playerStateChanged.on((e: { state: number }) => { if (!cancelled) setPlaying(e.state === 1); });
        api.tex(tex);
      } catch {
        if (!cancelled) setError("Failed to render tab.");
      }
    })();

    return () => {
      cancelled = true;
      api?.destroy();
      apiRef.current = null;
    };
  }, [url]);

  if (error) return <pre className="tab">{error}</pre>;
  return (
    <div>
      <div className="alphatab-controls">
        <button type="button" disabled={!ready} onClick={() => apiRef.current?.playPause()}>
          {ready ? (playing ? "❚❚ Pause" : "▶ Play") : "Loading sound…"}
        </button>
        <button type="button" disabled={!ready} onClick={() => apiRef.current?.stop()}>
          ■ Stop
        </button>
        <span className="muted" style={{ fontSize: 13 }}>cursor follows playback · click a note to jump</span>
      </div>
      <div className="alphatab" ref={ref} />
    </div>
  );
}
