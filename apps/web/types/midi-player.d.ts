// Minimal JSX typings for the html-midi-player web components.
import type React from "react";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "midi-player": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string;
          "sound-font"?: string | boolean;
          visualizer?: string;
        },
        HTMLElement
      >;
      "midi-visualizer": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string;
          type?: string;
        },
        HTMLElement
      >;
    }
  }
}
