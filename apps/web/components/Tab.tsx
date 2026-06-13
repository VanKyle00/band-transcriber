"use client";

import { useEffect, useState } from "react";

// ASCII tablature is generated server-side (pipeline/tab.py) and stored as a .txt
// artifact; here we just fetch and display it in a monospace block.
export default function Tab({ url }: { url: string }) {
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
