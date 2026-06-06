# Audiobook Maker - Project Memory & State

> **Shared project log.** Both Claude and Antigravity read and update this file. See `AGENTS.md` for the working agreement (layout, runtime, git rules). Keep this current after meaningful changes.

## Current Project Status
The Audiobook Maker is currently fully functional and running as a 24/7 background service on the host machine. The application automatically starts silently when the PC is booted. 

## Recent Updates & Accomplishments
0. **Warm Literary / Editorial Redesign (2026-06-06)**:
   - Reskinned the whole frontend to a "parchment & ink" literary aesthetic (frontend-design plugin style). Fonts switched from Inter to **Fraunces** (display) + **Newsreader** (body) serif; palette is cream/ink with terracotta + gold accents; cards are bookish (soft corners, paper shadow). Driven entirely through the existing CSS variables — no HTML/JS structure changes.
   - `:root` and `.theme-light` = bright parchment (now the default load); `.theme-dark` = "evening library" dark-academia (warm sepia/brown).
   - **Known follow-up:** `.theme-midnight`, `.theme-crimson`, `.theme-matcha` still carry their OLD neon palettes — they now clash with the serif fonts when selected. Either retune them to literary variants or trim the theme list. Theme-dropdown labels also still read "Dark/Light/Midnight Blue/..." (could be renamed to Parchment/Evening/etc.).
   - **TWO design directions are saved as branches (2026-06-06):** `master` / `design-literary` = this warm Literary look (**the chosen/active UI**). `design-ui-ux-pro-max` = an alternate "clean modern" redesign (Plus Jakarta Sans, teal semantic-token palette with `--on-primary` AA-contrast token, dark-mode parity, SVG brand icon instead of emoji, `:focus-visible` rings, `prefers-reduced-motion` support). Built by hand-applying two GitHub design skills (anthropics/claude-code `frontend-design` and nextlevelbuilder `ui-ux-pro-max`) — neither plugin is actually installed; the approaches were applied via direct edits. To preview the modern one: `git checkout design-ui-ux-pro-max` then restart the server; `git checkout master` to return to Literary.
1. **Major UI/UX Overhaul** (superseded by the 2026-06-06 redesign above for visual styling; functional features below still apply): 
   - Redesigned the web interface with modern aesthetics, glassmorphism, and dynamic animations.
   - Implemented 5 customizable UI themes (Dark, Light, Midnight Blue, Crimson, Matcha Green) via CSS variables.
   - Built a custom audio player with interactive controls (Play/Pause, Rewind/Skip 15s, Progress Scrubber) and a clickable chapter list to jump to specific points in the audiobook.
   - Added a visual step-by-step progress tracker (`detect` ➜ `extract` ➜ `ocr` ➜ `tts` ➜ `mux` ➜ `done`) and an overall 0-100% progress bar.

2. **Background Ambiance Feature**:
   - Integrated FFmpeg `amix` in `pipeline.py` to layer background ambiance tracks (e.g., Soft Rain, Crackling Fireplace) beneath the TTS narration.
   - Added a live browser preview on the main page so users can listen to the ambiance and adjust the volume slider in real-time before starting the generation job.

3. **Job Management Controls**:
   - Added the ability to dynamically **Pause** and **Resume** running jobs.
   - Added a **Delete / Stop** button to completely cancel a running job, clear it from the queue, and delete its files from the disk.

4. **Robust Error Handling & Bug Fixes**:
   - Fixed a critical bug where older jobs in the history (generated before the new metadata was introduced) would get stuck on a "Loading..." screen due to `NaN` calculations and unescaped Javascript syntax errors.
   - Modified the `/download` API endpoint to gracefully handle older jobs.

5. **24/7 Background Service Deployment**:
   - Created `web/run-background.vbs` and copied it to the Windows Startup folder (`shell:startup`) to launch the server silently.
   - Created `web/stop-audiobook-server.bat` as a utility tool to forcefully kill the hidden background Python server if needed.

## Key Files & Architecture
- `web/app.py`: The FastAPI server — routing, job queuing, file handling, the background **worker thread (inline in this file — there is no separate `worker.py`)**, and all the HTML/CSS/JS for the frontend.
- `web/pipeline.py`: Coordinates OCR parsing, FFmpeg muxing, and runs **Kokoro TTS in-process (local, not an external API)**.
- `web/start-audiobook-server.bat`: The standard batch script to launch the server (runs Uvicorn on `0.0.0.0:8765`).
- `web/run-background.vbs`: A VBScript wrapper that executes the batch file completely hidden in the background.

## Next Steps / Future Ideas
- Currently, the application uses local HTML/CSS/JS inside the `app.py` file. If the front-end grows more complex, it could be extracted into distinct static files or a React/Next.js frontend.
- Consider adding more background ambiance tracks or allowing users to upload their own custom ambient MP3/WAV files.
