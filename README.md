# Audiobook Maker

Turn an EPUB into a chaptered audiobook on your own machine. Upload a book in the web UI, pick a voice, and get an `.m4b` with chapter markers, narrated by a neural TTS model running locally on your GPU. No cloud APIs, no accounts, nothing leaves your PC.

Built for and daily-driven on one Windows machine. The server runs as a silent background service that starts on boot, and most listening happens from a phone over Tailscale.

## Features

- Handles both kinds of EPUBs. Text books are parsed directly; image-based (scanned) books go through Tesseract OCR with cleanup for page numbers, wrapped chapter titles, and OCR-mangled speaker labels.
- Narration by Kokoro TTS, running in-process on CUDA. Seven bundled voices with preview clips.
- Output is a chaptered `.m4b` muxed with ffmpeg, cover art included.
- Optional background ambiance (rain or fireplace) mixed under the narration, with a live preview of the blend before the job starts.
- A job queue with pause, resume, and cancel. Progress reports per phase: detect, extract or OCR, TTS, mux.
- A read-along reader. The book renders as turnable pages that follow the narration, the current sentence stays highlighted, and tapping a sentence seeks the audio to that point. Illustration pages from the source EPUB appear as full-page plates where they belong in the text. Three themes, including a true-black night mode for OLED screens.

## Design

One uvicorn process serves everything. `web/app.py` is the FastAPI server: JSON API, job queue, the worker thread, and static hosting of the built frontend. `web/pipeline.py` does the work — EPUB type detection, OCR or text extraction, TTS synthesis, m4b muxing. The UI is a Next.js 15 + TypeScript app in `frontend/`, exported statically. The build output in `frontend/out/` is committed on purpose: the boot-time server serves it from disk, so production needs no Node at all.

Keeping production to a single Python process was the point. FastAPI serves the static export same-origin, so the client uses relative URLs and there is no CORS setup and no reverse proxy.

## Running it

This is a personal tool, tuned to one PC, so there is no installer. To stand it up elsewhere:

1. Create a Python 3.11 virtual environment (PyTorch does not support newer yet). Install the CUDA build of PyTorch, then `fastapi`, `uvicorn`, `kokoro`, `soundfile`, `numpy`, `pytesseract`, and `Pillow`.
2. Put `ffmpeg` and `Tesseract` on PATH.
3. Edit the host IP in `web/start-audiobook-server.bat`. It deliberately binds to one specific interface (a Tailscale address) instead of `0.0.0.0`, so the server is not reachable from shared Wi-Fi. Pick the address that fits your network.
4. Run the bat file and open `http://<host>:8765`.

There is no authentication, so bind it to an interface you trust.

Frontend development needs Node: `npm --prefix frontend install` once, then `npm --prefix frontend run dev` for the dev loop and `npm --prefix frontend run build` to refresh `frontend/out/` before committing. Working notes for the whole project live in `AGENTS.md` and `PROJECT_MEMORY.md`.

## Samples

The bundled test book, `samples/yellow-wallpaper.epub`, is "The Yellow Wallpaper" by Charlotte Perkins Gilman (1892), public domain. The WAV files under `samples/out/` are Kokoro narrations of it, and `samples/voices/` holds the voice preview clips.

## Credits

Kokoro TTS (hexgrad), ffmpeg, Tesseract OCR, FastAPI, Next.js.
