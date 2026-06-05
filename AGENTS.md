# AGENTS.md — Audiobook Maker working agreement

Shared conventions for any AI tool working on this project (Claude Code, Antigravity, etc.).
**Read this first.** Goal: Claude and Antigravity can both edit this repo without clobbering each other.

## What this is
Local EPUB → audiobook web app. Upload an `.epub`, pick a voice, get a chaptered `.m4b`.
Auto-detects image-based epubs (runs OCR) vs text epubs. Runs entirely on this PC (GPU TTS).

## Layout
- `web/app.py` — FastAPI server: routes, job queue, **the worker thread (inline, NOT a separate file)**, and all HTML/CSS/JS for the frontend.
- `web/pipeline.py` — processing: `detect_mode` → `run_ocr`/`run_text` → `synth_book` (Kokoro) → `mux_m4b` (ffmpeg + mutagen chapters).
- `samples/voices/*.wav` — voice preview clips (served at `/voice-sample/{id}`).
- `ambiance/*.wav` — background ambiance tracks (rain, fire).
- `web/jobs/` — per-run output (gitignored; regenerated).
- `*.py` in root (`ocr_book.py`, `tts_book.py`, etc.) — standalone CLI versions, kept for reference.

## Runtime
- Python **3.11** venv at `A:\Cowork\audiobooks\.venv` (system Python is 3.14 — too new for PyTorch).
- PyTorch **cu128** (RTX 5090 / Blackwell). Kokoro runs **in-process** (local, not an external API).
- `ffmpeg` (winget Gyan) + `Tesseract` (winget UB-Mannheim) required on PATH.
- Server runs on **port 8765** (8000 is taken by SportsSphere/Docker — do NOT use 8000).

## Running it
- Start: `web/start-audiobook-server.bat` (uvicorn on `0.0.0.0:8765`).
- A hidden copy **auto-starts on boot** via `web/run-background.vbs` (in Windows Startup). Stop it with `web/stop-audiobook-server.bat`.
- **No auto-reload:** after editing code you MUST restart the server for changes to take effect.

## Collaboration rules (the important part)
1. **Git is the source of truth.** Run `git status` before you start; commit after every meaningful change with a clear message.
2. **One tool at a time.** Don't have Claude and Antigravity editing simultaneously. Commit/hand off between sessions.
3. **Never commit** `.venv/`, `web/jobs/`, generated audio, or scratch (already in `.gitignore`).
4. **Log what you did** in `PROJECT_MEMORY.md` (shared project log, read/written by both tools).
5. File naming: **kebab-case** (Alassane's preference).
6. Keep the frontend inline in `app.py` for now (don't split into a framework unless asked).

## Don't
- Don't switch the port off 8765. Don't delete other tools' work without committing first. Don't add heavy deps without noting them here + in PROJECT_MEMORY.md.
