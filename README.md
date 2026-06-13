# 🎚️ Band Transcriber

Take a song (uploaded audio **or** a YouTube link), separate it into instrument
**stems**, and transcribe each stem into **sheet music (PDF), tablature, MIDI/MusicXML,
and an interactive piano roll** — in the browser.

- **Core stems** (drums, bass, vocals): solid quality.
- **Guitar & piano**: best-effort / **experimental** (polyphonic transcription is hard —
  they're clearly labelled in the UI and never block the rest of a job).

Per the original request: **drums get sheet music**; **guitar & bass get tabs + sheet
music**. All pitched stems also get MIDI, MusicXML, and a piano-roll view.

---

## How it works

```
Browser (Next.js / Vercel)
  └─ POST file or URL ─► Next.js /api/jobs ─► Modal `web` (FastAPI)
                                                  └─ spawns process_job (CPU)
                                                        ├─ download   (yt-dlp + ffmpeg)
                                                        ├─ separate   (Demucs, GPU)  ← only GPU step
                                                        └─ per stem (CPU, fanned out):
                                                              transcribe → notation/tab → upload
  Browser polls /api/jobs/:id ◄─ reads job row ◄─ Supabase (jobs table + artifacts bucket)
```

Only Demucs runs on a GPU; everything else is CPU, which keeps serverless GPU cost to
**~$0.02–0.04 per song** (see [`docs/hosting-cost-chart.md`](docs/hosting-cost-chart.md)).

### Toolchain

| Stage | Tool | Notes |
|---|---|---|
| Download | yt-dlp + ffmpeg | file upload is the reliable path; YouTube is best-effort |
| Separation | Demucs `htdemucs_6s` (MIT) | 6 stems incl. guitar/piano |
| Drums → notes | librosa onset + spectral-band classifier | kick/snare/hi-hat → GM percussion MIDI |
| Bass/vocals → notes | Spotify basic-pitch | strong on isolated monophonic |
| Guitar/piano → notes | **MT3** (Modal GPU); basic-pitch fallback | heavier polyphonic model; still experimental |
| MIDI → tab | **open-fret** (guitar, when weights present) → `tab.py` assigner fallback | learned fingering when trained; deterministic ASCII otherwise |
| MIDI → MusicXML → PDF | music21 + LilyPond | headless engraving |
| Browser viewers | OpenSheetMusicDisplay, html-midi-player | sheet music + piano roll |

> MT3 runs in its own Modal GPU image (`mt3_image` in `modal_app.py`) because its
> JAX/T5X stack conflicts with the PyTorch/TF base image. The local CLI and the CPU base
> image have no MT3, so guitar/piano transcribe via basic-pitch there — set in
> `MT3_STEMS` (config.py). Guitar tab fingering uses **open-fret** (`pipeline/opentab.py`,
> `OPENFRET_STEMS`) when a trained checkpoint is present, else the deterministic assigner.
> Further swappable upgrades documented inline: `htdemucs_ft` for core separation,
> omnizart for drums.

---

## Repo layout

```
band-transcriber/
  modal_app.py              # Modal deployment (GPU separate + CPU fan-out + web endpoints)
  pipeline/                 # the pipeline (importable + locally runnable)
    config.py               #   per-stem behaviour (the single source of truth)
    download.py separate.py notation.py tab.py storage.py pipeline.py
    transcribe/             #   drums.py, melodic.py, dispatch
    cli.py                  #   local runner: python -m pipeline.cli ...
    tests/                  #   dependency-light unit tests (tab + config)
  apps/web/                 # Next.js app (Vercel)
  supabase/migrations/      # jobs table + artifacts bucket + TTL cleanup
  docs/hosting-cost-chart.md
```

---

## Setup

### Prerequisites
- Python 3.11 (the Modal image pins 3.11; the heavy ML deps don't yet support 3.13+).
- Node 18+.
- Accounts: [Modal](https://modal.com), [Supabase](https://supabase.com), [Vercel](https://vercel.com).

### 1. Supabase
```bash
# Apply the migration (via the Supabase SQL editor or CLI):
supabase db push        # or paste supabase/migrations/0001_init.sql into the SQL editor
```
This creates the `jobs` table and a private `artifacts` bucket. To enable automatic
TTL cleanup, turn on the `pg_cron` extension and uncomment the `cron.schedule(...)` line
at the bottom of the migration.

Grab your **project URL** and **service-role key** (Settings → API).

### 2. Modal
```bash
pip install modal && modal token new
# Store Supabase creds as a Modal secret the functions expect:
modal secret create band-transcriber-supabase \
  SUPABASE_URL=https://<proj>.supabase.co \
  SUPABASE_SERVICE_KEY=<service-role-key> \
  ARTIFACT_BUCKET=artifacts
# Optional: route yt-dlp through a residential proxy to dodge cloud-IP blocks
#   ...add YTDLP_PROXY=http://user:pass@host:port to the secret above

modal deploy modal_app.py
```
Deploy prints the **`web` endpoint URL** — that's your `MODAL_WEB_URL`.

### 3. Web app (Vercel)
```bash
cd apps/web
cp .env.example .env.local   # fill in MODAL_WEB_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY
npm install
npm run dev                  # http://localhost:3000
# Deploy: push to a repo and import in Vercel, or `vercel` (set the 3 env vars in the dashboard).
```

---

## Run the pipeline locally (no cloud needed)

The pipeline runs end-to-end on a laptop — without Supabase, artifacts are written under
`--out` and the printed manifest contains local paths. You still need the ML deps and
ffmpeg/LilyPond installed locally (heavy; this is mainly for debugging a single stage):

```bash
pip install -r pipeline/requirements.txt
python -m pipeline.cli --input song.wav --out ./bt-out
python -m pipeline.cli --input "https://youtu.be/..." --url
```

---

## Verification

```bash
# Pure logic (no ML deps) — runs anywhere:
python -m pytest pipeline/tests          # 13 tests: tab assignment + stem config

# Frontend:
cd apps/web && npx tsc --noEmit && npx next build

# Pipeline on Modal (GPU):
modal run modal_app.py::process_job --job-id smoke --source song.wav --is-url false
#   then check the `jobs` row + the artifacts bucket in Supabase.

# Web end-to-end: submit a short clip in the browser and confirm all four output
# types render and the guitar/piano panels show the "experimental" badge.
```

End-to-end success criteria: each artifact opens (PDF in a viewer, MIDI in a DAW,
MusicXML in MuseScore, tab in any text view), and core stems (drums/bass/vocals) are
recognizably correct by ear.

---

## Known limitations (by design)

- **YouTube from cloud IPs** is frequently rate-limited/blocked and is a ToS gray area.
  Uploading the file is the robust path; set `YTDLP_PROXY` for a residential proxy.
- **Guitar/piano transcription** uses MT3 on Modal (heavier polyphonic model) but is still
  experimental — polyphonic audio→notes is unsolved; never blocks a job. **MT3's
  jax/t5x/mt3 stack is version-sensitive**: the `mt3_image` pins in `modal_app.py` are a
  starting point and must be validated on Modal (you may need to nudge jax/flax/orbax to
  match current `t5x` main). MT3 also bakes a ~1 GB checkpoint into its image at build.
- **Drum transcription** here is a lightweight onset+band classifier (kick/snare/hi-hat).
  Swap in omnizart for richer kits.
- **MIDI playback in the piano roll**: `html-midi-player` pulls a `@magenta/music`/`tone`
  combo with a version skew that prints a build warning and can break *audio playback*
  (the piano-roll *visualization* still works). Pin a compatible `tone` if you need
  in-browser playback audio.
- **Guitar tablature via open-fret** is wired but **dormant by default**: open-fret ships
  no public weights (you train them via its repo), so until a checkpoint is mounted at
  `OPENFRET_MODEL_DIR` the pipeline uses the deterministic fret assigner. To activate,
  mount/bake a trained `tiny-tab-v1/final` dir there (e.g. a Modal Volume) — its AlphaTex
  output then renders cleanly in alphaTab (a frontend follow-up).
- Tracks are capped at **8 minutes** to bound GPU cost (`MAX_DURATION_SEC` in config).

## Adding accounts later

v1 is intentionally one-shot/ephemeral (no login; rows + files expire in 24h). To add a
saved library: add a `user_id` column to `jobs`, add Supabase Auth, and add per-user RLS
policies. No pipeline changes required.
