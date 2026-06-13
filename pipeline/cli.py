"""Local CLI for running the full pipeline without Modal/Supabase.

    python -m pipeline.cli --input song.wav --out ./bt-out
    python -m pipeline.cli --input "https://youtu.be/..." --url

With no Supabase env vars set, artifacts are written under --out and the printed
manifest contains local file paths instead of signed URLs.
"""
from __future__ import annotations

import argparse
import json
import uuid

from .config import DEFAULT_STEMS, STEMS
from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate + transcribe a song into stems.")
    parser.add_argument("--input", required=True, help="audio/video file path, or URL with --url")
    parser.add_argument("--url", action="store_true", help="treat --input as a URL (yt-dlp)")
    parser.add_argument("--out", default="./bt-out", help="working/output directory")
    parser.add_argument("--stems", default=",".join(DEFAULT_STEMS),
                        help=f"comma-separated subset of: {','.join(STEMS)}")
    parser.add_argument("--proxy", default=None, help="proxy URL for yt-dlp")
    args = parser.parse_args()

    stems = tuple(s for s in (x.strip() for x in args.stems.split(",")) if s in STEMS)
    job_id = uuid.uuid4().hex[:12]
    manifest = run_pipeline(job_id, args.input, args.url, stems, args.out, args.proxy)
    print(json.dumps({"job_id": job_id, **manifest}, indent=2))


if __name__ == "__main__":
    main()
