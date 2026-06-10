"""
Audiobook web app — JSON API + static frontend server.

The UI is a Next.js app in frontend/, exported to frontend/out and served
by this same FastAPI process, so one server on port 8765 covers PC and
phone (Tailscale). Frontend dev mode: `npm --prefix frontend run dev`
(next dev on :3000, proxying API calls here).

Run via web/start-audiobook-server.bat (sets ffmpeg PATH + binds host).
No auto-reload: restart after editing this file.
"""
import os, re, json, uuid, queue, shutil, threading, traceback, datetime, time

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import pipeline

BASE = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE, "jobs")
FRONTEND_OUT = os.path.normpath(os.path.join(BASE, "..", "frontend", "out"))
TRANSFER = r"D:\Transfer\Audiobooks"
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(TRANSFER, exist_ok=True)

app = FastAPI()
jobs = {}                      # id -> dict
job_q = queue.Queue()

for jid in os.listdir(JOBS_DIR):
    st_path = os.path.join(JOBS_DIR, jid, "status.json")
    if os.path.exists(st_path):
        try:
            with open(st_path, "r", encoding="utf-8") as f:
                j = json.load(f)
                j["dir"] = os.path.join(JOBS_DIR, jid)
                ch_path = os.path.join(j["dir"], "_chapters.txt")
                if "chapters_info" not in j and os.path.exists(ch_path):
                    ch_info = []
                    with open(ch_path, "r", encoding="utf-8") as cf:
                        title, start = "", 0
                        for line in cf.read().splitlines():
                            if line.startswith("START="):
                                start = int(line.split("=")[1]) / 1000.0
                            elif line.startswith("title="):
                                title = line.split("=", 1)[1]
                                if title and title != j.get("base"):
                                    ch_info.append({"title": title, "start": start})
                    j["chapters_info"] = ch_info
                jobs[jid] = j
        except Exception:
            pass


def save_status(job):
    try:
        with open(os.path.join(job["dir"], "status.json"), "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in job.items() if k != "dir"}, f)
    except Exception:
        pass


# Each phase maps onto a slice of the single 0..1 progress bar, so it only
# ever moves forward (OCR/extract = first third, narration = the rest).
PHASE_RANGE = {
    "detect": (0.00, 0.02), "extract": (0.02, 0.35), "ocr": (0.02, 0.35),
    "tts": (0.35, 0.98), "mux": (0.98, 0.99), "done": (1.0, 1.0),
}


def set_progress(job):
    def cb(phase, frac, message):
        while job.get("status") == "paused":
            time.sleep(1)
        if job.get("status") == "cancelled":
            raise RuntimeError("Job cancelled by user.")
        lo, hi = PHASE_RANGE.get(phase, (0.0, 1.0))
        job["phase"] = phase
        job["frac"] = round(lo + max(0.0, min(frac, 1.0)) * (hi - lo), 3)
        job["message"] = message
        if job.get("status") != "cancelled":
            save_status(job)
    return cb


def worker():
    while True:
        jid = job_q.get()
        job = jobs.get(jid)
        if not job or job.get("status") == "cancelled":
            job_q.task_done()
            continue
        cb = set_progress(job)
        try:
            job["status"] = "running"
            cb("detect", 0.0, "Inspecting epub...")
            mode = pipeline.detect_mode(job["epub"])
            job["mode"] = mode
            cb("detect", 0.05, f"Detected: {'image-based (OCR needed)' if mode=='ocr' else 'text-based'}")

            if mode == "ocr":
                chapters = pipeline.run_ocr(job["epub"], job["dir"], cb)
            else:
                chapters = pipeline.run_text(job["epub"], job["dir"], cb)
            if not chapters:
                raise RuntimeError("No readable text found in this epub.")
            job["chapters_total"] = len(chapters)

            cover = pipeline.get_cover(job["epub"], job["dir"], mode)
            durations = pipeline.synth_book(chapters, job["voice"], job["dir"], cb,
                                            speed=job["speed"])

            t = 0.0
            ch_info = []
            for ctitle, _, dur in durations:
                ch_info.append({"title": ctitle, "start": round(t, 3)})
                t += dur
            job["chapters_info"] = ch_info

            cb("mux", 0.99, "Packaging .m4b ...")
            out_m4b = os.path.join(job["dir"], job["base"] + ".m4b")
            pipeline.mux_m4b(durations, job["dir"], cover, out_m4b,
                             title=job["base"], artist="Audiobook", bitrate=job["bitrate"],
                             ambiance=job.get("ambiance"), amb_vol=job.get("amb_vol", 10))

            dest = os.path.join(TRANSFER, job["base"] + ".m4b")
            shutil.copy2(out_m4b, dest)
            total_min = sum(d for _, _, d in durations) / 60
            job["status"] = "done"
            job["output"] = out_m4b
            job["transfer"] = dest
            job["minutes"] = round(total_min, 1)
            cb("done", 1.0, f"Done — {len(chapters)} chapters, {total_min/60:.1f} h. Copied to Transfer.")
        except Exception as e:
            if str(e) == "Job cancelled by user.":
                job["status"] = "cancelled"
            else:
                job["status"] = "error"
                job["error"] = f"{e}\n{traceback.format_exc()}"
                job["message"] = f"Error: {e}"
        finally:
            if job.get("status") != "cancelled":
                save_status(job)
            job_q.task_done()


threading.Thread(target=worker, daemon=True).start()


# ----------------------------------------------------------------- API
@app.get("/api/jobs")
def api_jobs():
    """Slim job list for the frontend's library section, newest first."""
    items = sorted(jobs.values(), key=lambda j: j.get("created", ""), reverse=True)
    out = []
    for j in items:
        if j.get("status") == "cancelled":
            continue
        out.append({
            "id": j["id"], "name": j.get("name", ""), "status": j.get("status", ""),
            "frac": j.get("frac", 0), "phase": j.get("phase"),
            "minutes": j.get("minutes"), "created": j.get("created", ""),
        })
        if len(out) >= 50:
            break
    return JSONResponse(out)


@app.get("/api/job/{jid}")
def api_job(jid: str):
    j = jobs.get(jid)
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k != "dir"})


@app.post("/upload")
def upload(file: UploadFile = File(...), voice: str = Form("af_heart"), speed: str = Form("1"), quality: str = Form("standard"), ambiance: str = Form(""), amb_vol: int = Form(10)):
    jid = uuid.uuid4().hex[:10]
    job_dir = os.path.join(JOBS_DIR, jid)
    os.makedirs(job_dir, exist_ok=True)

    base = file.filename.rsplit(".", 1)[0]
    base = re.sub(r'[^A-Za-z0-9_\-\.\s]', '', base).strip()
    if not base:
        base = "audiobook"

    epub_path = os.path.join(job_dir, "book.epub")
    with open(epub_path, "wb") as f:
        f.write(file.file.read())

    bitrate = {"compact": "32k", "standard": "64k", "high": "128k"}.get(quality, "64k")

    amb_path = None
    if ambiance == "rain": amb_path = os.path.join(BASE, "..", "ambiance", "rain.wav")
    elif ambiance == "fire": amb_path = os.path.join(BASE, "..", "ambiance", "fire.wav")

    job = {
        "id": jid, "name": file.filename, "base": base,
        "epub": epub_path, "voice": voice, "speed": float(speed),
        "bitrate": bitrate, "status": "queued",
        "ambiance": amb_path,
        "amb_vol": amb_vol,
        "created": datetime.datetime.now().isoformat(),
        "dir": job_dir
    }
    jobs[jid] = job
    save_status(job)
    job_q.put(jid)

    # The React app navigates itself; no redirect dance.
    return JSONResponse({"id": jid})


@app.post("/api/job/{jid}/delete")
def delete_job(jid: str):
    j = jobs.get(jid)
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)
    j["status"] = "cancelled"
    if jid in jobs:
        del jobs[jid]
    try:
        shutil.rmtree(j.get("dir", ""), ignore_errors=True)
    except Exception:
        pass
    return JSONResponse({"ok": True})


@app.post("/api/job/{jid}/pause")
def pause_job(jid: str):
    j = jobs.get(jid)
    if not j: return JSONResponse({"error": "not found"}, status_code=404)
    if j.get("status") == "running":
        j["status"] = "paused"
        save_status(j)
    return JSONResponse({"ok": True})


@app.post("/api/job/{jid}/resume")
def resume_job(jid: str):
    j = jobs.get(jid)
    if not j: return JSONResponse({"error": "not found"}, status_code=404)
    if j.get("status") == "paused":
        j["status"] = "running"
        save_status(j)
    return JSONResponse({"ok": True})


# ----------------------------------------------------------------- media
# Kokoro voice ids look like af_heart / bm_george; anything else (path
# separators, dots) is rejected before touching the filesystem.
VOICE_ID_RE = re.compile(r"^[a-z]{2}_[a-z0-9]+$")
AMBIANCE_NAMES = {"rain", "fire"}


@app.get("/voice-sample/{vid}")
def voice_sample(vid: str):
    if not VOICE_ID_RE.match(vid):
        return JSONResponse({"error": "not found"}, status_code=404)
    path = os.path.join(BASE, "..", "samples", "voices", f"{vid}.wav")
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="audio/wav")


@app.get("/download/{jid}")
def download(jid: str):
    j = jobs.get(jid)
    if not j or j.get("status") != "done":
        return HTMLResponse("Not ready or not found", status_code=404)
    out_m4b = os.path.join(j["dir"], j["base"] + ".m4b")
    if os.path.exists(out_m4b):
        return FileResponse(out_m4b, media_type="audio/mp4", filename=j["base"] + ".m4b")
    # Job folder may have been cleaned; the Transfer copy survives.
    transfer_m4b = os.path.join(TRANSFER, j["base"] + ".m4b")
    if os.path.exists(transfer_m4b):
        return FileResponse(transfer_m4b, media_type="audio/mp4", filename=j["base"] + ".m4b")
    return HTMLResponse("File missing", status_code=404)


@app.api_route("/stream/{jid}", methods=["GET", "HEAD"])
def stream(jid: str):
    # Separate from /download: the <audio> player needs the file served INLINE
    # (no attachment disposition) with an explicit audio MIME type and HTTP range
    # support. iOS Safari silently refuses to play attachment-dispositioned media,
    # which is why playback worked on desktop downloads but not on the phone.
    j = jobs.get(jid)
    if not j or j.get("status") != "done":
        return HTMLResponse("Not ready or not found", status_code=404)
    out_m4b = os.path.join(j["dir"], j["base"] + ".m4b")
    if os.path.exists(out_m4b):
        return FileResponse(out_m4b, media_type="audio/mp4")
    transfer_m4b = os.path.join(TRANSFER, j["base"] + ".m4b")
    if os.path.exists(transfer_m4b):
        return FileResponse(transfer_m4b, media_type="audio/mp4")
    return HTMLResponse("File missing", status_code=404)


@app.get("/ambiance/{name}")
def get_ambiance(name: str):
    if name not in AMBIANCE_NAMES:
        return HTMLResponse("Not found", 404)
    path = os.path.join(BASE, "..", "ambiance", f"{name}.wav")
    if os.path.exists(path):
        return FileResponse(path, media_type="audio/wav")
    return HTMLResponse("Not found", 404)


# ----------------------------------------------------------------- frontend
@app.get("/job/{jid}")
def legacy_job_page(jid: str):
    """Old bookmark/deep-link format → the exported job page."""
    return RedirectResponse(url=f"/job/?id={jid}", status_code=302)


if os.path.isdir(FRONTEND_OUT):
    # Mounted last so every /api, /upload, /stream… route above wins first.
    # html=True serves index.html for / and job/index.html for /job/.
    app.mount("/", StaticFiles(directory=FRONTEND_OUT, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def missing_frontend():
        return HTMLResponse(
            "<h1>Frontend not built</h1><p>Run <code>npm --prefix frontend install "
            "&amp;&amp; npm --prefix frontend run build</code> in A:\\Cowork\\audiobooks, "
            "then restart the server.</p>", status_code=503)
