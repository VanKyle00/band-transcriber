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
        if (cancelled || !ref.current) return;
        api = new alphaTab.AlphaTabApi(ref.current, {
          core: {
            useWorkers: false,
            fontDirectory:
              "https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.8.3/dist/font/",
          },
          player: { enablePlayer: false },
        } as any);
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
