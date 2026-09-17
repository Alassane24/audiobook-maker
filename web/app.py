"""
Audiobook web app — JSON API + static frontend server.

The UI is a Next.js app in frontend/, exported to frontend/out and served
by this same FastAPI process, so one server on port 8765 covers PC and
phone (Tailscale). Frontend dev mode: `npm --prefix frontend run dev`
(next dev on :3000, proxying API calls here).

Run via web/start-audiobook-server.bat (sets ffmpeg PATH + binds host).
No auto-reload: restart after editing this file.
"""
import os, re, json, uuid, queue, shutil, threading, traceback, datetime, time, mimetypes

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Python's mimetypes doesn't know .webmanifest, so StaticFiles would serve the
# PWA manifest as octet-stream and some browsers reject it. Register it before
# the mount below so it ships as application/manifest+json.
mimetypes.add_type("application/manifest+json", ".webmanifest")

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


TEXT_CACHE_VERSION = 2   # bump when extraction output changes shape/content


def save_chapters_text(job_dir, chapters):
    """The narrated text (+ illustration anchors), persisted for the reader."""
    try:
        payload = {"v": TEXT_CACHE_VERSION, "chapters": [
            {"title": c["title"], "text": c["text"], "images": c.get("images", [])}
            for c in chapters]}
        with open(os.path.join(job_dir, "chapters_text.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f)
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

            if mode == "pdf":
                chapters = pipeline.run_pdf(job["epub"], job["dir"], cb)
            elif mode == "ocr":
                chapters = pipeline.run_ocr(job["epub"], job["dir"], cb)
            else:
                chapters = pipeline.run_text(job["epub"], job["dir"], cb)
            if not chapters:
                raise RuntimeError("No readable text found in this epub.")
            job["chapters_total"] = len(chapters)
            save_chapters_text(job["dir"], chapters)

            cover = pipeline.get_cover(job["epub"], job["dir"], mode)
            marks = []
            durations = pipeline.synth_book(chapters, job["voice"], job["dir"], cb,
                                            speed=job["speed"], marks_out=marks)
            try:
                with open(os.path.join(job["dir"], "timing.json"), "w", encoding="utf-8") as tf:
                    json.dump(marks, tf)
            except Exception:
                pass

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


# ------------------------------------------------- read-along text
# Books rendered before the reader existed have no chapters_text.json.
# First /text request kicks a one-time background rebuild from the job's
# stored epub (re-OCR for scanned books — minutes; instant for text epubs)
# and the endpoint reports 202 + progress until the cache lands.
text_builds = {}   # jid -> {"state": "building"|"error", "progress": float, "message": str}


def _norm_title(s):
    s = re.sub(r"[=;#\\]", " ", s or "")   # the mux writes titles with these stripped
    return re.sub(r"\s+", " ", s).strip().casefold()


def _align_text_to_audio(chapters, audio_titles):
    """Re-bucket freshly extracted text chapters to match the audiobook's
    chapter list. Cleaning rules evolve between renders, so a re-extraction
    can split chapters the audio merged, invent fragments from OCR noise,
    or glue prose onto a title. Titles are matched normalized (exact or
    prefix, forward-only); unmatched fragments fold into the current
    bucket. Falls back to the raw extraction if too little matches."""
    if not audio_titles:
        return chapters
    norm_audio = [_norm_title(t) for t in audio_titles]
    texts = [""] * len(audio_titles)
    images = [[] for _ in audio_titles]
    cur, matched = 0, set()
    for c in chapters:
        nt = _norm_title(c.get("title", ""))
        hit = None
        for i in range(cur, len(norm_audio)):
            na = norm_audio[i]
            if not na or not nt:
                continue
            if nt == na or (min(len(nt), len(na)) >= 12 and (nt.startswith(na) or na.startswith(nt))):
                hit = i
                break
        if hit is not None:
            cur = hit
            matched.add(hit)
        # Folding a fragment shifts its char offsets by the text already
        # in the bucket (+1 for the joining space).
        base = len(texts[cur]) + 1 if texts[cur] else 0
        for img in c.get("images", []):
            images[cur].append({"char": base + img.get("char", 0), "file": img.get("file", "")})
        texts[cur] = (texts[cur] + " " + c["text"]).strip() if texts[cur] else c["text"]
    if len(matched) < max(1, len(audio_titles) // 2):
        return chapters
    return [{"title": audio_titles[i], "text": texts[i], "images": images[i]}
            for i in range(len(audio_titles))]


def _build_text(jid):
    j = jobs.get(jid)
    b = text_builds[jid]
    try:
        if not j:
            raise RuntimeError("Job no longer exists.")
        epub_path = j.get("epub", "")
        if not os.path.exists(epub_path):
            raise RuntimeError("Original epub no longer exists for this job.")
        mode = j.get("mode") or pipeline.detect_mode(epub_path)

        def cb(phase, frac, message):
            b["progress"] = round(max(0.0, min(frac, 1.0)), 3)
            b["message"] = message

        if mode == "pdf":
            chapters = pipeline.run_pdf(epub_path, j["dir"], cb)
        elif mode == "ocr":
            chapters = pipeline.run_ocr(epub_path, j["dir"], cb)
        else:
            chapters = pipeline.run_text(epub_path, j["dir"], cb)
        if not chapters:
            raise RuntimeError("No readable text found in this epub.")
        audio_titles = [c.get("title", "") for c in (j.get("chapters_info") or [])]
        chapters = _align_text_to_audio(chapters, audio_titles)
        save_chapters_text(j["dir"], chapters)
        text_builds.pop(jid, None)
    except Exception as e:
        b["state"] = "error"
        b["message"] = str(e)


@app.get("/api/job/{jid}/text")
def job_text(jid: str):
    j = jobs.get(jid)
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)

    text_path = os.path.join(j["dir"], "chapters_text.json")
    if os.path.exists(text_path):
        try:
            with open(text_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None
        # Old/stale cache shapes (the v1 bare list, pre-illustrations)
        # fall through to a rebuild instead of being served.
        if isinstance(data, dict) and data.get("v") == TEXT_CACHE_VERSION:
            timing = None
            timing_path = os.path.join(j["dir"], "timing.json")
            if os.path.exists(timing_path):
                try:
                    with open(timing_path, "r", encoding="utf-8") as f:
                        timing = json.load(f)
                except Exception:
                    timing = None
            return JSONResponse({"chapters": data["chapters"], "timing": timing})

    b = text_builds.get(jid)
    if b and b["state"] == "error":
        msg = b["message"]
        text_builds.pop(jid, None)   # allow retry on the next request
        return JSONResponse({"error": msg}, status_code=500)
    if not b:
        text_builds[jid] = {"state": "building", "progress": 0.0, "message": "Starting…"}
        threading.Thread(target=_build_text, args=(jid,), daemon=True).start()
    b = text_builds.get(jid) or {"progress": 1.0, "message": "Finishing…"}
    return JSONResponse({"building": True, "progress": b.get("progress", 0.0),
                         "message": b.get("message", "")}, status_code=202)


@app.post("/upload")
def upload(file: UploadFile = File(...), voice: str = Form("af_heart"), speed: str = Form("1"), quality: str = Form("standard"), ambiance: str = Form(""), amb_vol: int = Form(10)):
    jid = uuid.uuid4().hex[:10]
    job_dir = os.path.join(JOBS_DIR, jid)
    os.makedirs(job_dir, exist_ok=True)

    base = file.filename.rsplit(".", 1)[0]
    ext = file.filename.rsplit(".", 1)[-1].lower()
    base = re.sub(r'[^A-Za-z0-9_\-\.\s]', '', base).strip()
    if not base:
        base = "audiobook"

    # Save as .pdf if uploaded a PDF, otherwise .epub
    book_filename = "book.pdf" if ext == "pdf" else "book.epub"
    epub_path = os.path.join(job_dir, book_filename)
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
PAGE_IMAGE_RE = re.compile(r"^[A-Za-z0-9._-]+\.(jpg|jpeg|png)$", re.I)


@app.get("/api/job/{jid}/page-image/{name}")
def page_image(jid: str, name: str):
    """Illustration scans referenced by the read-along reader."""
    j = jobs.get(jid)
    if not j or not PAGE_IMAGE_RE.match(name) or ".." in name:
        return JSONResponse({"error": "not found"}, status_code=404)
    path = os.path.normpath(os.path.join(j["dir"], "_images", name))
    if not path.startswith(os.path.normpath(j["dir"])) or not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    media = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    return FileResponse(path, media_type=media)


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
JOB_ID_RE = re.compile(r"^[0-9a-f]{8,12}$")


@app.get("/job/{jid}")
def legacy_job_page(jid: str):
    """Old bookmark/deep-link format /job/<hexid> → the exported job page.

    Anything else under /job/ belongs to the static export — most
    importantly Next's RSC navigation payload /job/index.txt, which this
    route would otherwise hijack and break client-side navigation.
    """
    if JOB_ID_RE.match(jid):
        return RedirectResponse(url=f"/job/?id={jid}", status_code=302)
    path = os.path.normpath(os.path.join(FRONTEND_OUT, "job", jid))
    if path.startswith(FRONTEND_OUT) and os.path.isfile(path):
        media = "text/x-component" if path.endswith(".txt") else None
        return FileResponse(path, media_type=media)
    return HTMLResponse("Not found", status_code=404)


if os.path.isdir(FRONTEND_OUT):
    # Next's exported RSC payloads are .txt files; the router only treats
    # a response as a client-side navigation payload when it arrives as
    # text/x-component, otherwise every tap degrades to a full reload.
    class FrontendFiles(StaticFiles):
        def file_response(self, full_path, stat_result, scope, status_code=200):
            resp = super().file_response(full_path, stat_result, scope, status_code)
            p = str(full_path).replace("\\", "/")
            if p.endswith(".txt"):
                resp.headers["content-type"] = "text/x-component"
            # Caching: hashed build assets under _next/static are immutable
            # (the filename changes when the content does), so cache them hard.
            # index.html and the RSC .txt payloads must always revalidate, or a
            # new build never loads on a normal refresh — that's what left the
            # desktop app stuck on a stale "phone view" cached page.
            if "/_next/static/" in p:
                resp.headers["cache-control"] = "public, max-age=31536000, immutable"
            elif p.endswith(".html") or p.endswith(".txt"):
                resp.headers["cache-control"] = "no-cache"
            return resp

    # Mounted last so every /api, /upload, /stream… route above wins first.
    # html=True serves index.html for / and job/index.html for /job/.
    app.mount("/", FrontendFiles(directory=FRONTEND_OUT, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def missing_frontend():
        return HTMLResponse(
            "<h1>Frontend not built</h1><p>Run <code>npm --prefix frontend install "
            "&amp;&amp; npm --prefix frontend run build</code> in A:\\Cowork\\audiobooks, "
            "then restart the server.</p>", status_code=503)
