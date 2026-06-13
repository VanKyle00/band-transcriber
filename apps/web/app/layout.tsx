import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Band Transcriber",
  description: "Separate any song into stems and transcribe them to sheet music, tabs, and MIDI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link href="/" className="brand">🎚️ Band Transcriber</Link>
          <nav>
            <Link href="/">Transcribe</Link>
            <Link href="/cost">Hosting cost</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
