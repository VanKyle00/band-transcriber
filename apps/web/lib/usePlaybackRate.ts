import { useEffect, type RefObject } from "react";

// Apply a playback rate to an <audio> while preserving pitch, so "slow it down"
// lowers the tempo without making everything sound lower. preservesPitch is the
// standard property; webkitPreservesPitch covers older Safari. No dependency array:
// the rate is re-applied on every render so it sticks even when the audio element
// mounts on a later render than this hook's first run.
export function usePlaybackRate(ref: RefObject<HTMLAudioElement | null>, rate: number) {
  useEffect(() => {
    const a = ref.current;
    if (!a) return;
    a.playbackRate = rate;
    a.preservesPitch = true;
    (a as HTMLAudioElement & { webkitPreservesPitch?: boolean }).webkitPreservesPitch = true;
  });
}
