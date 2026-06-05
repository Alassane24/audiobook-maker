# Audiobook Maker - Project Memory & State

## Current Project Status
The Audiobook Maker is currently fully functional and running as a 24/7 background service on the host machine. The application automatically starts silently when the PC is booted. 

## Recent Updates & Accomplishments
1. **Major UI/UX Overhaul**: 
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
- `web/app.py`: The FastAPI server containing the routing, job queuing, file handling, and HTML templates (including all the new CSS and Javascript for the frontend).
- `web/worker.py`: Background thread processor that monitors the job queue, updates statuses, and executes the pipeline.
- `web/pipeline.py`: Coordinates the FFmpeg processing, OCR parsing, and interacts with the external Kokoro TTS API.
- `web/start-audiobook-server.bat`: The standard batch script to launch the server (runs Uvicorn on `0.0.0.0:8765`).
- `web/run-background.vbs`: A VBScript wrapper that executes the batch file completely hidden in the background.

## Next Steps / Future Ideas
- Currently, the application uses local HTML/CSS/JS inside the `app.py` file. If the front-end grows more complex, it could be extracted into distinct static files or a React/Next.js frontend.
- Consider adding more background ambiance tracks or allowing users to upload their own custom ambient MP3/WAV files.
