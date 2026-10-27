# Self-hosted AI (DPDP-compliant, in-India)

This stack replaces the US-hosted Groq endpoints with **open-source models you run yourself**, so
call audio and transcripts never leave your infrastructure. There is then no cross-border transfer
of personal data to justify under the DPDP Act.

Both services expose the **OpenAI API**, so the backend swap is config only — the same
`TRANSCRIPTION_BASE_URL` / `LLM_BASE_URL` / `EMBEDDING_BASE_URL` it already uses.

## What's in it

| Job | Service | Default model | Why |
|-----|---------|---------------|-----|
| Speech-to-text | [Speaches](https://github.com/speaches-ai/speaches) (faster-whisper) | `faster-whisper-large-v3` | True OpenAI drop-in; large-v3 handles Indian languages. Upgrade path: AI4Bharat **IndicConformer** (all 22 languages) once A/B-tested on your real telephony audio. |
| LLM (briefs, summaries, "ask") | [vLLM](https://docs.vllm.ai) | `sarvamai/sarvam-m` (24B, Apache-2.0) | Indian-made, all 22 languages incl. romanized; single-GPU friendly when quantized. |

## Requirements
- A server **physically located in India** (your cloud region's India zone, or on-prem).
- Docker + NVIDIA Container Toolkit, and an NVIDIA GPU (defaults assume ~24 GB).
- A Hugging Face token (some model downloads are gated): set `HUGGING_FACE_HUB_TOKEN`.

## Run
```bash
cp .env.sample .env        # set HUGGING_FACE_HUB_TOKEN
docker compose up -d
# first start downloads the models (several GB) - watch: docker compose logs -f
```

## Point the CRM backend at it
In the backend's own `.env` (NOT this folder's), set:
```
AI_DATA_PROCESSING_ENABLED=true
TRANSCRIPTION_BASE_URL=http://<ai-host>:8001/v1
TRANSCRIPTION_MODEL=Systran/faster-whisper-large-v3
LLM_BASE_URL=http://<ai-host>:8002/v1
LLM_MODEL=sarvamai/sarvam-m
EMBEDDING_BASE_URL=http://<ai-host>:8002/v1
EMBEDDING_MODEL=sarvamai/sarvam-m
```
Keep `<ai-host>` on a private network with the backend; don't expose 8001/8002 publicly.

## Hardware variants
- **One mid GPU (~24 GB, default):** as shipped — large-v3 + Sarvam-M AWQ.
- **One big / multi-GPU (40–80 GB+):** drop `--quantization awq`, raise `--max-model-len`, or move
  to Sarvam 30B/105B; add `--tensor-parallel-size N` across cards.
- **CPU only (start compliant now, no GPU yet):** set the transcription image to the non-CUDA
  `ghcr.io/speaches-ai/speaches:latest-cpu` with a smaller Whisper model, and either run a small LLM
  (e.g. Qwen/Llama 7–8B) on CPU — slow — or set `AI_DATA_PROCESSING_ENABLED=false` so the app runs
  fully offline (manual-text recap instead of AI briefs) until a GPU is available.

## The DPDP kill-switch
`AI_DATA_PROCESSING_ENABLED=false` makes the backend send **nothing** to any AI endpoint —
transcription, LLM and embeddings all fall back to offline stubs — regardless of the URLs above.
A hard guarantee that no audio/text leaves the server, useful during audits or incidents.

## Before you rely on this for production
- Benchmark `large-v3` vs IndicConformer on a labelled set of your **own** call recordings
  (8 kHz telephony, code-mixed) and keep the lower word-error-rate one.
- Confirm the GPU host, its backups, and its logs are all inside India too — the model is only one
  part of the data path.
