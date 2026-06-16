import type { Metadata } from "next";
import { Bricolage_Grotesque, Nunito } from "next/font/google";
import Link from "next/link";

import "./globals.css";

// Warm display + body pair from the friendly "Practice Buddy" redesign. Exposed as CSS
// variables so the warm components (loading screen, speed control) can opt in without
// changing the rest of the app's type.
const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-bricolage",
});
const nunito = Nunito({
  subsets: ["latin"],
  weight: ["400", "600", "700", "800"],
  variable: "--font-nunito",
});

export const metadata: Metadata = {
  title: "Band Transcriber",
  description: "Separate any song into stems and transcribe them to sheet music, tabs, and MIDI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${bricolage.variable} ${nunito.variable}`}>
        <header className="site-header">
          <Link href="/" className="brand">
            <span className="brand-logo" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            Band Transcriber
          </Link>
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
