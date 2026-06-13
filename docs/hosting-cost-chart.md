# Hosting cost chart — stem separation on serverless GPU

> Verified mid-2026. Serverless GPU bills per-second and scales to zero, so you pay
> only for audio you actually process. "Per song" = one ~3.5-minute track through the
> full pipeline. GPU-time budget assumed ≈ **90–180 GPU-seconds/song** (Demucs
> `htdemucs_6s` + a couple of transcription passes); the lighter transcription/notation
> steps run on cheap CPU. Ranges below reflect that budget. Always confirm against live
> pricing pages before committing — GPU prices move.

## A. Serverless GPU price ($/hour)

| Provider | T4 | L4 | A10/A10G | L40S | A100-80GB | H100 | Cold start | Scale-to-0 |
|---|---|---|---|---|---|---|---|---|
| **Modal** | $0.59 | $0.80 | $1.10 | $1.95 | $2.50 | $3.95 | <5 s | ✅ |
| **RunPod (Flex)** | — | ~$0.39 | ~$0.44 | ~$0.86 | ~$1.39 | ~$4.18 | 5–20 s | ✅ |
| **Replicate** | $0.81 | — | — | $3.51 | $5.04 | $5.49 | ~11 s | partial |
| **fal.ai** | — | — | — | — | $1.08 | $1.80 (H100) | ~2–5 s | ✅ |
| **Beam** | — | — | ~$1.05 | $0.72 | $1.30 | — | ~5 s | ✅ |

Notes:
- RunPod per-second figures are derived from published hourly rates (÷3600); RunPod
  emphasizes hourly billing. "Active" workers are ~20% cheaper than "Flex" but keep a
  warm baseline (you pay for idle).
- Replicate has a narrow GPU menu and keeps *pre-built* models warm; custom deployments
  still cold-start.
- fal.ai and Beam list mainly higher-end GPUs; good if you want faster wall-clock.

## B. Estimated cost per 3.5-min song (cheapest viable, L4-class)

| Provider / GPU | $ per song | Notes |
|---|---|---|
| **RunPod Flex · L4** | **~$0.01–0.02** | cheapest; more DevOps (build/push Docker images) |
| **Modal · L4** ⭐ | **~$0.02–0.04** | best ergonomics for a custom multi-step pipeline; <5 s cold start |
| **Modal · T4** | ~$0.015–0.03 | budget; slower, fine for v1 |
| **fal.ai · A100** | ~$0.03–0.05 | faster wall-clock |
| **Replicate · T4** | ~$0.02–0.05 | simplest for off-the-shelf models; clunky for custom pipelines |

## C. Monthly projection (Modal · L4, ~$0.03/song incl. CPU steps)

| Volume / month | Compute | + Vercel/Supabase | Notes |
|---|---|---|---|
| 100 songs | ~$3 | free tiers | hobby |
| 1,000 songs | ~$30 | mostly free tiers | small product |
| 10,000 songs | ~$300 | ~$25–50 storage/egress | consider RunPod Active or a reserved GPU |

## D. Third-party stem-separation APIs (no hosting — for comparison)

| Service | ~$/min audio | ~$/3.5-min song | Note |
|---|---|---|---|
| AudioShake (bulk API) | $0.01–0.05 | $0.04–0.18 | per-minute, volume pricing |
| Music.ai (5-stem) | $0.07 | ~$0.25 | per-stem pricing |
| LALAL.AI | $0.06 (Pro) | ~$0.21 | minute packs; minutes = duration × #stems |
| Moises Pro | ~$0.10 | ~$0.35 | highest quality; subscription/API |

These return **stems only** — they do not transcribe to notation/tabs, which is the
hard, value-adding half of this project.

## Recommendation

Build v1 on **Modal + L4**: scale-to-zero, sub-5 s cold start, ~$0.02–0.04/song, and the
best developer experience for a custom `download → separate → transcribe → render`
pipeline (you write plain Python functions with a `gpu=` decorator). If pure cost at
scale (10k+/month) becomes the priority, the same container ports to **RunPod Flex**.
Reach for a third-party stem API only if you want zero GPU ops — but accept paying
5–10× more per song and losing the transcription/notation step.

## Sources (accessed mid-2026)

GPU pricing: [Modal](https://modal.com/pricing) ·
[Replicate](https://replicate.com/pricing) ·
[RunPod](https://www.runpod.io/pricing) ·
[fal.ai](https://fal.ai/pricing) ·
[Beam](https://www.beam.cloud/pricing)

Demucs performance/VRAM: [facebookresearch/demucs](https://github.com/facebookresearch/demucs) ·
[StemSplit Demucs setup guide](https://stemsplit.io/blog/demucs-local-setup-guide) ·
[Demucs paper](https://arxiv.org/pdf/2006.12847)

Stem APIs: [LALAL.AI](https://www.lalal.ai/pricing/) ·
[Music.ai](https://music.ai/pricing/) ·
[Moises](https://stemsplit.io/blog/moises-ai-review) ·
[AudioShake pricing analysis](https://www.oreateai.com/blog/unpacking-audioshake-ai-pricing-what-you-need-to-know)
