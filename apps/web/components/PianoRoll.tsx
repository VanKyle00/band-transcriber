"use client";

import { useEffect } from "react";

// Interactive piano roll + playback via the html-midi-player web components.
// Importing the module registers the <midi-player> / <midi-visualizer> elements.
export default function PianoRoll({ url, id }: { url: string; id: string }) {
  useEffect(() => {
    // Package ships no type declarations; imported only for its registration side effect.
    // @ts-expect-error - no types for html-midi-player
    import("html-midi-player");
  }, []);

  const visId = `vis-${id}`;
  return (
    <div>
      <midi-visualizer id={visId} type="piano-roll" src={url} />
      <midi-player src={url} sound-font visualizer={`#${visId}`} style={{ width: "100%" }} />
    </div>
  );
}
