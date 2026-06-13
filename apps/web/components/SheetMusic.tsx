"use client";

import { useEffect, useRef } from "react";

// Renders a MusicXML score in-browser with OpenSheetMusicDisplay. We fetch the
// XML as text first (avoids any cross-origin quirks with OSMD's own loader).
export default function SheetMusic({ url }: { url: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let osmd: { clear?: () => void } | null = null;
    let cancelled = false;

    (async () => {
      const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
      const xml = await fetch(url).then((r) => r.text());
      if (cancelled || !host.current) return;
      const display = new OpenSheetMusicDisplay(host.current, {
        autoResize: true,
        drawingParameters: "compact",
      });
      osmd = display;
      await display.load(xml);
      if (!cancelled) display.render();
    })().catch((e) => console.error("OSMD render failed", e));

    return () => {
      cancelled = true;
      osmd?.clear?.();
    };
  }, [url]);

  return <div className="osmd" ref={host} />;
}
