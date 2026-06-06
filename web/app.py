"""
Audiobook web app. Run:
    .venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
Then open http://<this-PC-ip>:8000 from your phone or PC.
"""
import os, re, json, uuid, queue, shutil, threading, traceback, datetime, html, time

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse

import pipeline

BASE = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE, "jobs")
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

# ----------------------------------------------------------------- pages
PAGE_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Marcellus&family=Jost:wght@300;400;500;600;700&display=swap');
  * { box-sizing: border-box; }
  /* frontend-design direction: "Golden Age Broadcast" — Art Deco.
     Deep emerald-black + antique gold + cream. Marcellus (deco display serif)
     + Jost (geometric body). Dominant dark-luxe with sharp gold accents,
     gold hairline frames, spotlight atmosphere, staggered page-load reveal. */
  :root {
    /* Golden Age Broadcast — emerald & gold (default) */
    --bg: #0d1f17; --card: #122a20; --text: #f2e8ce; --text-muted: #9fae9b;
    --primary: #c8a24a; --on-primary: #14130b; --primary-hover: rgba(200,162,74,0.10); --accent: #d9b765;
    --accent-glow: rgba(200,162,74,0.30); --border: rgba(200,162,74,0.22);
    --bg-grad-1: rgba(200,162,74,0.12); --bg-grad-2: rgba(31,84,62,0.45); --play-bg: rgba(242,232,206,0.04);
  }
  .theme-dark {
    --bg: #0d1f17; --card: #122a20; --text: #f2e8ce; --text-muted: #9fae9b;
    --primary: #c8a24a; --on-primary: #14130b; --primary-hover: rgba(200,162,74,0.10); --accent: #d9b765;
    --accent-glow: rgba(200,162,74,0.30); --border: rgba(200,162,74,0.22);
    --bg-grad-1: rgba(200,162,74,0.12); --bg-grad-2: rgba(31,84,62,0.45); --play-bg: rgba(242,232,206,0.04);
  }
  .theme-light {
    /* Deco cream variant — bone & gold on green ink */
    --bg: #efe6cd; --card: #f8f1dd; --text: #14271d; --text-muted: #5a6450;
    --primary: #7a5c12; --on-primary: #fbf6e6; --primary-hover: rgba(122,92,18,0.08); --accent: #1d4a39;
    --accent-glow: rgba(122,92,18,0.22); --border: rgba(20,40,30,0.18);
    --bg-grad-1: rgba(154,123,34,0.10); --bg-grad-2: rgba(29,74,57,0.08); --play-bg: rgba(20,40,30,0.04);
  }
  .theme-midnight {
    --bg: #020617; --card: rgba(15, 23, 42, 0.8); --text: #f1f5f9; --text-muted: #94a3b8;
    --primary: #3b82f6; --primary-hover: rgba(59, 130, 246, 0.15); --accent: #8b5cf6;
    --accent-glow: rgba(139,92,246,0.5); --border: rgba(255, 255, 255, 0.06);
    --bg-grad-1: rgba(59,130,246,0.15); --bg-grad-2: rgba(139,92,246,0.1); --play-bg: rgba(255,255,255,0.06);
  }
  .theme-crimson {
    --bg: #1a0505; --card: rgba(40, 10, 10, 0.7); --text: #fee2e2; --text-muted: #fca5a5;
    --primary: #ef4444; --primary-hover: rgba(239, 68, 68, 0.15); --accent: #dc2626;
    --accent-glow: rgba(220,38,38,0.5); --border: rgba(255, 0, 0, 0.15);
    --bg-grad-1: rgba(239,68,68,0.1); --bg-grad-2: rgba(220,38,38,0.1); --play-bg: rgba(255,0,0,0.08);
  }
  .theme-matcha {
    --bg: #0f1c14; --card: rgba(18, 38, 25, 0.7); --text: #ecfdf5; --text-muted: #6ee7b7;
    --primary: #10b981; --primary-hover: rgba(16, 185, 129, 0.15); --accent: #059669;
    --accent-glow: rgba(5,150,105,0.5); --border: rgba(16, 185, 129, 0.15);
    --bg-grad-1: rgba(16,185,129,0.1); --bg-grad-2: rgba(5,150,105,0.1); --play-bg: rgba(16,185,129,0.08);
  }

  body {
    font-family: 'Jost', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    background-image: radial-gradient(ellipse 80% 55% at 50% -8%, var(--bg-grad-1) 0%, transparent 55%),
                      radial-gradient(circle at 88% 12%, var(--bg-grad-2) 0%, transparent 42%),
                      radial-gradient(circle at 8% 94%, var(--bg-grad-2) 0%, transparent 46%);
    background-attachment: fixed;
    color: var(--text);
    margin: 0 auto;
    padding: 48px 24px 90px;
    max-width: 760px;
    line-height: 1.65;
    transition: background 0.5s ease, color 0.5s ease;
  }
  /* One orchestrated page-load moment: a deliberate curtain-rise sequence */
  @keyframes fadeUp { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes iconIn { from { opacity: 0; transform: scale(0.6) rotate(-8deg); } to { opacity: 1; transform: scale(1) rotate(0); } }
  .brand { animation: fadeUp 0.6s cubic-bezier(0.16,1,0.3,1) both; }
  .brand-icon { animation: iconIn 0.7s cubic-bezier(0.16,1,0.3,1) 0.05s both; }
  .sub { animation: fadeUp 0.6s cubic-bezier(0.16,1,0.3,1) 0.12s both; }
  .card { animation: fadeUp 0.7s cubic-bezier(0.16,1,0.3,1) both; }
  .card:nth-of-type(1) { animation-delay: 0.2s; }
  .card:nth-of-type(2) { animation-delay: 0.3s; }
  .card:nth-of-type(3) { animation-delay: 0.4s; }
  .brand { display: flex; align-items: center; gap: 13px; margin-bottom: 6px; }
  .brand-icon { color: var(--primary); display: flex; align-items: center; filter: drop-shadow(0 0 10px var(--accent-glow)); }
  h1 { font-size: 34px; font-weight: 400; margin: 0; font-family: 'Marcellus', Georgia, serif; color: var(--text); letter-spacing: 0.01em; line-height: 1.05; }
  .sub { color: var(--text-muted); margin: 4px 0 36px; font-size: 16px; font-weight: 500; font-family: 'Jost', system-ui, sans-serif; }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 38px;
    margin: 26px 0;
    box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset, inset 0 0 0 1px rgba(200,162,74,0.06), 0 24px 50px -28px rgba(0,0,0,0.6);
    transition: transform 0.3s ease, border-color 0.3s ease;
  }
  .card:hover { border-color: var(--rule, var(--border)); }
  h2 { font-size: 13px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--primary); font-weight: 600; font-family: 'Jost', system-ui, sans-serif; margin: 0 0 18px; display: flex; align-items: center; gap: 14px; }
  h2::after { content: ''; flex: 1; display: block; height: 1px; background: var(--border); }
  label { display: block; font-size: 13px; letter-spacing: 0.12em; font-weight: 600; color: var(--text-muted); margin-bottom: 12px; text-transform: uppercase; font-family: 'Jost', system-ui, sans-serif; }
  
  .drop {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    border: 2px dashed var(--border); border-radius: 20px; padding: 40px 20px; text-align: center;
    background: var(--primary-hover); cursor: pointer; transition: all 0.2s ease; color: var(--text-muted); font-size: 15px; font-weight: 500;
  }
  .drop svg { margin-bottom: 12px; color: var(--primary); transition: transform 0.2s; }
  .drop:hover { border-color: var(--primary); background: var(--primary-hover); color: var(--text); }
  .drop:hover svg { transform: translateY(-4px); }
  .drop.has { border-color: var(--primary); background: var(--primary-hover); color: var(--primary); }
  .drop.has svg { color: var(--primary); }
  input[type=file] { display: none; }
  
  .voices { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media(max-width:560px) { .voices { grid-template-columns: 1fr; } }
  .voice {
    display: flex; align-items: center; gap: 16px; border: 1.5px solid var(--border); border-radius: 16px;
    padding: 14px 16px; cursor: pointer; transition: all 0.2s ease; background: var(--play-bg);
  }
  .voice:hover { border-color: var(--primary-hover); background: var(--primary-hover); transform: translateY(-2px); }
  .voice.sel { border-color: var(--primary); background: var(--primary-hover); box-shadow: 0 0 0 4px var(--primary-hover); }
  
  .play {
    flex: none; width: 44px; height: 44px; border-radius: 50%; border: 0; background: var(--play-bg); color: var(--text);
    cursor: pointer; transition: all 0.2s ease; display: grid; place-items: center; padding: 0;
  }
  .play svg { width: 20px; height: 20px; fill: currentColor; margin-left: 2px; }
  .play:hover { background: var(--primary); color: white; transform: scale(1.08); box-shadow: 0 4px 12px var(--accent-glow); }
  .play.playing { background: linear-gradient(135deg, var(--primary), var(--accent)); color: #fff; animation: pulse 2s infinite; }
  .play.playing svg { margin-left: 0; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 var(--accent-glow); } 70% { box-shadow: 0 0 0 10px rgba(0,0,0,0); } 100% { box-shadow: 0 0 0 0 rgba(0,0,0,0); } }
  
  .vmeta { flex: 1; min-width: 0; }
  .vname { font-weight: 400; font-size: 19px; color: var(--text); margin-bottom: 2px; font-family: 'Marcellus', Georgia, serif; }
  .vtag { font-size: 12px; color: var(--primary); font-weight: 600; }
  .vdesc { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  
  .speedrow { display: flex; align-items: center; gap: 20px; background: var(--play-bg); padding: 16px 20px; border-radius: 16px; border: 1px solid var(--border); }
  input[type=range] { flex: 1; accent-color: var(--primary); height: 6px; background: var(--border); border-radius: 3px; outline: none; -webkit-appearance: none; cursor: pointer; }
  input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 18px; height: 18px; background: var(--primary); border-radius: 50%; box-shadow: 0 2px 6px rgba(0,0,0,0.3); }
  .speedval { font-weight: 700; color: var(--text); min-width: 54px; text-align: right; font-variant-numeric: tabular-nums; font-size: 16px; }
  
  .pills { display: flex; gap: 12px; }
  .pill {
    flex: 1; text-align: center; padding: 14px 8px; border: 1.5px solid var(--border); border-radius: 16px; cursor: pointer;
    font-weight: 600; font-size: 15px; color: var(--text-muted); transition: all 0.2s ease; background: var(--play-bg); line-height: 1.3;
  }
  .pill small { display: block; font-weight: 500; font-size: 12px; color: var(--text-muted); margin-top: 4px; }
  .pill:hover { border-color: var(--primary-hover); background: var(--primary-hover); color: var(--text); transform: translateY(-2px); }
  .pill.sel { border-color: var(--primary); background: var(--primary-hover); color: var(--text); box-shadow: 0 0 0 4px var(--primary-hover); }
  .pill.sel small { color: var(--primary); }
  
  button.go {
    width: 100%; padding: 18px; margin-top: 32px; border: 0; border-radius: 6px; cursor: pointer;
    background: var(--primary); color: var(--on-primary, #fff); font-size: 14px; font-weight: 600; font-family: 'Jost', system-ui, sans-serif; letter-spacing: 0.18em; text-transform: uppercase;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 10px 22px -8px var(--accent-glow);
    display: flex; align-items: center; justify-content: center; gap: 10px;
  }
  button.go:hover { transform: translateY(-3px); box-shadow: 0 20px 35px -10px var(--accent-glow); filter: brightness(1.1); }
  button.go:active { transform: translateY(0); }
  
  .row { display: flex; justify-content: space-between; align-items: center; transition: background 0.2s; margin: 0 -16px; padding: 16px; border-radius: 12px; }
  .row:hover { background: var(--play-bg); }
  .row:last-child { border-bottom: 0; }
  a { color: var(--primary); text-decoration: none; font-weight: 600; transition: color 0.2s; }
  a:hover { color: var(--accent); }
  
  .tag { display: inline-flex; align-items: center; gap: 7px; font-size: 11px; padding: 4px 11px; border-radius: 7px; background: var(--play-bg); color: var(--text-muted); border: 1px solid var(--border); font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
  .tag::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); flex: none; }
  .ok { color: var(--text); }
  .ok::before { background: #34d399; box-shadow: 0 0 7px rgba(52,211,153,0.75); }
  .err { color: var(--text); }
  .err::before { background: #f87171; box-shadow: 0 0 7px rgba(248,113,113,0.75); }
  
  .muted { color: var(--text-muted); font-size: 14px; font-weight: 500; }
  .bar { height: 14px; background: rgba(0,0,0,0.3); border-radius: 8px; overflow: hidden; margin: 20px 0; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); border: 1px solid var(--border); }
  .fill { height: 100%; width: 0; background: linear-gradient(90deg, var(--primary), var(--accent)); transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1); border-radius: 8px; box-shadow: 0 0 10px var(--accent-glow); }
  .dl { display: inline-flex; align-items: center; justify-content: center; gap: 12px; margin-top: 20px; padding: 17px 28px; background: var(--primary); color: var(--on-primary, #fff); border-radius: 6px; font-weight: 600; font-size: 13px; font-family: 'Jost', system-ui, sans-serif; letter-spacing: 0.18em; text-transform: uppercase; transition: all 0.2s; box-shadow: 0 10px 22px -8px var(--accent-glow); text-decoration: none; width: 100%; }
  .dl:hover { transform: translateY(-2px); box-shadow: 0 15px 28px -10px var(--accent-glow); filter: brightness(1.06); color: var(--on-primary, #fff); }

  select {
    width: 100%; padding: 12px 16px; border-radius: 12px; background: var(--play-bg); color: var(--text);
    border: 1px solid var(--border); font-size: 15px; font-weight: 600; outline: none; cursor: pointer;
    font-family: 'Jost', sans-serif;
  }
  select:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-hover); }
  select option { background: var(--bg); color: var(--text); }
  
  .theme-select {
    padding: 6px 12px; border-radius: 8px; background: var(--play-bg); color: var(--text); border: 1px solid var(--border); font-size: 13px; font-weight: 600; cursor: pointer; width: auto;
  }

  /* Chapter list scrollbar — slim, themed (replaces chunky default) */
  .ch-list { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
  .ch-list::-webkit-scrollbar { width: 8px; }
  .ch-list::-webkit-scrollbar-track { background: transparent; margin: 6px 0; }
  .ch-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 8px; border: 2px solid transparent; background-clip: padding-box; }
  .ch-list::-webkit-scrollbar-thumb:hover { background: var(--text-muted); background-clip: padding-box; }

  /* Accessibility (ui-ux-pro-max CRITICAL rules): visible keyboard focus + reduced-motion */
  :focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 6px; }
  .voice:focus-visible, .pill:focus-visible { outline-offset: 4px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
  }
</style>"""


VOICE_CARDS = [
    ("af_heart",   "Heart",   "American · Warm",  "Natural & warm — default"),
    ("af_bella",   "Bella",   "American · Crisp", "Clear and articulate"),
    ("af_nicole",  "Nicole",  "American · Soft",  "Soft, breathy"),
    ("am_michael", "Michael", "American · Male",  "Neutral narrator"),
    ("am_fenrir",  "Fenrir",  "American · Deep",  "Deeper male voice"),
    ("bf_emma",    "Emma",    "British · Female", "Classic audiobook"),
    ("bm_george",  "George",  "British · Male",   "British male"),
]

SAMPLES_DIR = r"A:\Cowork\audiobooks\samples\voices"


def render_voices():
    out = []
    svg_play = '<svg viewBox="0 0 24 24"><path d="M7 4l13 8-13 8V4z"/></svg>'
    for vid, name, tag, desc in VOICE_CARDS:
        sel = " sel" if vid == "af_heart" else ""
        out.append(
            f'<div class="voice{sel}" data-id="{vid}" onclick="pick(this)">'
            f'<button type="button" class="play" onclick="event.stopPropagation();preview(this,\'{vid}\')">{svg_play}</button>'
            f'<div class="vmeta"><div class="vname">{name}</div>'
            f'<div class="vtag">{tag}</div><div class="vdesc">{desc}</div></div></div>')
    return "\n".join(out)


def recent_rows():
    items = sorted(jobs.values(), key=lambda j: j.get("created", ""), reverse=True)[:12]
    if not items:
        return '<p class="muted">No audiobooks yet.</p>'
    rows = []
    for j in items:
        st = j.get("status", "")
        if st == "cancelled": continue
        cls = {"done": "ok", "error": "err"}.get(st, "")
        link = f'<a href="/job/{j["id"]}">{html.escape(j["name"])}</a>'
        del_btn = f'<button onclick="delJob(\'{j["id"]}\')" title="Delete audiobook" style="display:inline-flex; align-items:center; gap:6px; background:transparent; border:1px solid var(--border); cursor:pointer; color:var(--text-muted); padding:6px 12px; border-radius:8px; font-weight:600; font-size:12px; transition:all 0.18s; font-family:inherit;" onmouseover="this.style.borderColor=\'#ef4444\'; this.style.color=\'#ef4444\'; this.style.background=\'rgba(239,68,68,0.08)\';" onmouseout="this.style.borderColor=\'var(--border)\'; this.style.color=\'var(--text-muted)\'; this.style.background=\'transparent\';"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>Delete</button>'
        rows.append(f'<div class="row" id="row-{j["id"]}"><div style="flex:1;">{link} <span class="tag {cls}" style="margin-left:8px;">{st}</span></div>{del_btn}</div>')
    return "".join(rows)


@app.get("/", response_class=HTMLResponse)
def index():
    page = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audiobook Maker</title>__CSS__
<script>
  let thm = localStorage.getItem('theme') || 'theme-dark';
  document.documentElement.className = thm;
  function setT(v) { document.documentElement.className = v; localStorage.setItem('theme', v); }
</script>
</head><body>
<div style="display:flex; justify-content:space-between; align-items:center;">
  <div class="brand"><span class="brand-icon" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 9v6"/><path d="M9 5v14"/><path d="M14 8v8"/><path d="M19 6v12"/></svg></span><h1>Audiobook Maker</h1></div>
  <select class="theme-select" onchange="setT(this.value)">
    <option value="theme-dark">Dark</option>
    <option value="theme-light">Light</option>
    <option value="theme-midnight">Midnight Blue</option>
    <option value="theme-crimson">Crimson</option>
    <option value="theme-matcha">Matcha Green</option>
  </select>
</div>
<p class="sub">Drop in an EPUB, pick a voice, and get a beautifully narrated audiobook.</p>
<div class="card">
 <form action="/upload" method="post" enctype="multipart/form-data">
  <label>Book Source</label>
  <label class="drop" id="drop">
   <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h14a2 2 0 0 0 2-2V7.5L14.5 2H6a2 2 0 0 0-2 2v4"/><polyline points="14 2 14 8 20 8"/><path d="M2 15h10"/><path d="M9 18l3-3-3-3"/></svg>
   <span id="dropt" style="margin-top:12px; font-weight:600;">Choose an .epub file</span>
   <span style="font-size:12px; font-weight:400; opacity:0.7; margin-top:4px;">or drag and drop it here</span>
   <input type="file" name="file" accept=".epub" required id="file">
  </label>
  <label style="margin-top:32px">Select Narrator &nbsp;&middot;&nbsp; Tap play to preview</label>
  <div class="voices">__VOICES__</div>
  <input type="hidden" name="voice" id="voice" value="af_heart">

  <label style="margin-top:32px">Narration Speed</label>
  <div class="speedrow">
   <input type="range" name="speed" id="speed" min="0.5" max="2" step="0.1" value="1">
   <span class="speedval" id="speedval">1.0&times;</span>
  </div>

  <div style="display:flex; gap:16px; margin-top:32px;">
    <div style="flex:1;">
      <label>Background Ambiance</label>
      <select name="ambiance" id="amb_select">
        <option value="">None</option>
        <option value="rain">Soft Rain</option>
        <option value="fire">Crackling Fireplace</option>
      </select>
    </div>
    <div style="flex:1;">
      <label>Ambiance Volume</label>
      <div class="speedrow" style="margin-top:0; padding:12px 16px;">
        <input type="range" name="amb_vol" id="amb_vol" min="0" max="100" step="5" value="10">
        <span class="speedval" id="volval" style="min-width:44px;">10%</span>
      </div>
    </div>
  </div>

  <label style="margin-top:32px">Output Quality</label>
  <div class="pills">
   <div class="pill" data-q="compact" onclick="pickq(this)">Compact<small>smaller file</small></div>
   <div class="pill sel" data-q="standard" onclick="pickq(this)">Standard<small>recommended</small></div>
   <div class="pill" data-q="high" onclick="pickq(this)">High<small>best fidelity</small></div>
  </div>
  <input type="hidden" name="quality" id="quality" value="standard">

  <button class="go" type="submit">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
    Generate Audiobook
  </button>
 </form>
</div>
<div class="card"><h2>Recent Jobs</h2>__RECENT__</div>
<script>
const SVG_PLAY = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4l13 8-13 8V4z"/></svg>';
const SVG_PAUSE = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
const SVG_CHECK = '<svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>';

var file=document.getElementById('file'),drop=document.getElementById('drop'),dt=document.getElementById('dropt');
file.addEventListener('change',function(){
    if(file.files[0]){
        dt.innerHTML=SVG_CHECK + '<br>' + file.files[0].name;
        drop.classList.add('has');
        drop.querySelector('svg').style.display='none';
    }
});
drop.addEventListener('dragover', function(e){e.preventDefault(); drop.style.borderColor='#818cf8'; drop.style.background='rgba(99, 102, 241, 0.1)';});
drop.addEventListener('dragleave', function(e){e.preventDefault(); drop.style.borderColor=''; drop.style.background='';});
drop.addEventListener('drop', function(e){
  e.preventDefault(); drop.style.borderColor=''; drop.style.background='';
  if(e.dataTransfer.files.length){
    file.files = e.dataTransfer.files;
    dt.innerHTML=SVG_CHECK + '<br>' + file.files[0].name;
    drop.classList.add('has');
    drop.querySelector('svg').style.display='none';
  }
});
function pick(el){document.querySelectorAll('.voice').forEach(function(v){v.classList.remove('sel');});el.classList.add('sel');document.getElementById('voice').value=el.dataset.id;}
var sp=document.getElementById('speed');
function curSpeed(){return parseFloat(sp.value)||1;}
sp.addEventListener('input',function(){
 document.getElementById('speedval').innerHTML=curSpeed().toFixed(1)+'&times;';
 if(aud){aud.playbackRate=curSpeed();}
});
var vsl=document.getElementById('amb_vol');
var ambAud=document.createElement('audio'); ambAud.loop=true;
document.getElementById('amb_select').addEventListener('change', function(){
  if(this.value) { ambAud.src='/ambiance/'+this.value; ambAud.volume=curAmbVol()/100; ambAud.play(); }
  else { ambAud.pause(); }
});
function curAmbVol(){ return vsl ? (parseFloat(vsl.value)||0) : 10; }
if(vsl) { 
  vsl.addEventListener('input',function(){ 
    document.getElementById('volval').innerText=vsl.value+'%'; 
    ambAud.volume = curAmbVol()/100;
  }); 
}

function pickq(el){document.querySelectorAll('.pill').forEach(function(p){p.classList.remove('sel');});el.classList.add('sel');document.getElementById('quality').value=el.dataset.q;}
var aud=null,curBtn=null;
document.querySelector('select.theme-select').value = document.documentElement.className || 'theme-dark';
function reset(b){if(b){b.classList.remove('playing');b.innerHTML=SVG_PLAY;}}
function preview(btn,id){
 if(ambAud) ambAud.pause(); document.getElementById('amb_select').value='';
 if(aud&&curBtn===btn){aud.pause();reset(btn);aud=null;curBtn=null;return;}
 if(aud){aud.pause();reset(curBtn);}
 aud=new Audio('/voice-sample/'+id);curBtn=btn;btn.classList.add('playing');btn.innerHTML=SVG_PAUSE;
 aud.preservesPitch=true;aud.mozPreservesPitch=true;aud.webkitPreservesPitch=true;
 aud.playbackRate=curSpeed();
 aud.play().catch(function(){reset(btn);aud=null;curBtn=null;});
 aud.onended=function(){reset(btn);aud=null;curBtn=null;};
}
async function delJob(jid) {
  if (!confirm("Are you sure you want to stop/delete this job?")) return;
  await fetch("/api/job/" + jid + "/delete", {method: "POST"});
  let row = document.getElementById("row-" + jid);
  if (row) row.remove();
}
</script>
</body></html>"""
    return page.replace("__CSS__", PAGE_CSS).replace("__VOICES__", render_voices()).replace("__RECENT__", recent_rows())


@app.get("/voice-sample/{vid}")
def voice_sample(vid: str):
    path = os.path.join(SAMPLES_DIR, f"{vid}.wav")
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="audio/wav")


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

    return RedirectResponse(url=f"/job/{jid}", status_code=303)


@app.get("/api/job/{jid}")
def api_job(jid: str):
    j = jobs.get(jid)
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k != "dir"})

@app.post("/api/job/{jid}/delete")
def delete_job(jid: str):
    j = jobs.get(jid)
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)
    j["status"] = "cancelled"
    if jid in jobs:
        del jobs[jid]
    import shutil
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


@app.get("/job/{jid}", response_class=HTMLResponse)
def job_page(jid: str):
    j = jobs.get(jid)
    if not j:
        return HTMLResponse("Job not found", status_code=404)
    
    html_name = html.escape(j['name'])
    page = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__</title>__CSS__
<script>
  let thm = localStorage.getItem('theme') || 'theme-dark';
  document.documentElement.className = thm;
  function setT(v) { document.documentElement.className = v; localStorage.setItem('theme', v); }
</script>
</head><body>
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
  <div class="brand"><span class="brand-icon" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 9v6"/><path d="M9 5v14"/><path d="M14 8v8"/><path d="M19 6v12"/></svg></span><h1>Audiobook Maker</h1></div>
  <select class="theme-select" onchange="setT(this.value)">
    <option value="theme-dark">Dark</option>
    <option value="theme-light">Light</option>
    <option value="theme-midnight">Midnight Blue</option>
    <option value="theme-crimson">Crimson</option>
    <option value="theme-matcha">Matcha Green</option>
  </select>
</div>
<div class="sub" style="display:flex; justify-content:space-between; align-items:center;">
 <span>Job Details &middot; __NAME__</span>
 <div style="display:flex; gap:8px;">
   <button id="btn-pause" onclick="togglePause('__JID__')" style="display:none; background:rgba(245, 158, 11, 0.1); border:1px solid rgba(245, 158, 11, 0.3); color:#fbbf24; border-radius:8px; padding:6px 12px; cursor:pointer; font-weight:600; font-size:13px; transition:all 0.2s;">Pause</button>
   <button id="btn-resume" onclick="toggleResume('__JID__')" style="display:none; background:rgba(34, 197, 94, 0.1); border:1px solid rgba(34, 197, 94, 0.3); color:#4ade80; border-radius:8px; padding:6px 12px; cursor:pointer; font-weight:600; font-size:13px; transition:all 0.2s;">Resume</button>
   <button onclick="delJob('__JID__')" style="background:rgba(239, 68, 68, 0.1); border:1px solid rgba(239, 68, 68, 0.3); color:#f87171; border-radius:8px; padding:6px 12px; cursor:pointer; font-weight:600; font-size:13px; transition:all 0.2s;" onmouseover="this.style.background='rgba(239, 68, 68, 0.2)'" onmouseout="this.style.background='rgba(239, 68, 68, 0.1)'">Stop / Delete</button>
 </div>
</div>
<div class="card" style="margin-bottom:24px;">
 <div style="display:flex; justify-content:space-between; margin-bottom:32px; position:relative; max-width:400px; margin-left:auto; margin-right:auto; margin-top:8px;">
  <div style="position:absolute; top:50%; left:0; right:0; height:2px; background:var(--border); z-index:0; transform:translateY(-50%);"></div>
  <div id="track-line" style="position:absolute; top:50%; left:0; width:0%; height:2px; background:var(--primary); z-index:0; transform:translateY(-50%); transition:width 0.5s;"></div>
  
  <div class="step-dot" id="dot-ocr" style="z-index:1; background:var(--card); padding:5px 14px; color:var(--text-muted); font-size:12px; font-weight:600; border-radius:12px; border:2px solid var(--border); transition:all 0.3s;">Reading</div>
  <div class="step-dot" id="dot-tts" style="z-index:1; background:var(--card); padding:5px 14px; color:var(--text-muted); font-size:12px; font-weight:600; border-radius:12px; border:2px solid var(--border); transition:all 0.3s;">Narrating</div>
  <div class="step-dot" id="dot-mux" style="z-index:1; background:var(--card); padding:5px 14px; color:var(--text-muted); font-size:12px; font-weight:600; border-radius:12px; border:2px solid var(--border); transition:all 0.3s;">Finishing</div>
 </div>

 <div id="msg" style="font-size:16px; font-weight:600; color:#f8fafc; margin-bottom:12px; text-align:center;">Loading...</div>
 <div class="bar" style="height:12px; border-radius:6px; overflow:hidden; background:#334155;"><div class="fill" id="fill" style="height:100%; transition:width 0.5s;"></div></div>
 <div style="display:flex; justify-content:space-between; margin-top:12px; font-size:13px; color:#94a3b8; font-weight:600;">
  <span id="mode" style="text-transform:none; letter-spacing:0.2px;"></span>
  <span id="pct" style="color:#f8fafc;">0%</span>
 </div>
</div>
 <div class="muted" id="sub"></div>
 <div id="result"></div>
</div>
<p><a href="/" style="display:inline-flex; align-items:center; gap:6px; background:rgba(255,255,255,0.05); padding:10px 16px; border-radius:12px; transition:all 0.2s;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg> Create New Audiobook</a></p>
<script>
const I_PLAY = '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4l13 8-13 8V4z"/></svg>';
const I_PAUSE = '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
const I_RW = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path><text x="12.4" y="15.4" font-size="8.5" font-weight="700" stroke="none" fill="currentColor" text-anchor="middle" font-family="Inter,system-ui,sans-serif">15</text></svg>';
const I_FF = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path><path d="M21 3v5h-5"></path><text x="11.6" y="15.4" font-size="8.5" font-weight="700" stroke="none" fill="currentColor" text-anchor="middle" font-family="Inter,system-ui,sans-serif">15</text></svg>';

function fmtT(s) {
    let m=Math.floor(s/60), sec=Math.floor(s%60), h=Math.floor(m/60); m=m%60;
    return h>0 ? h+":"+(m<10?"0":"")+m+":"+(sec<10?"0":"")+sec : m+":"+(sec<10?"0":"")+sec;
}
function tglP() {
    let a=document.getElementById('player'), b=document.getElementById('playBtn');
    if(a.paused){a.play(); b.innerHTML=I_PAUSE; b.style.paddingLeft='0';}
    else{a.pause(); b.innerHTML=I_PLAY; b.style.paddingLeft='4px';}
}
function skp(amt) { document.getElementById('player').currentTime += amt; }
function onT() {
    let a=document.getElementById('player'); if(!a.duration) return;
    document.getElementById('pBar').value = (a.currentTime/a.duration)*100;
    document.getElementById('cT').textContent = fmtT(a.currentTime);
}
function onL() { document.getElementById('tT').textContent = fmtT(document.getElementById('player').duration); }
function onS(v) { let a=document.getElementById('player'); if(a.duration) a.currentTime = (v/100)*a.duration; }

async function poll(){
 try {
  const r = await fetch('/api/job/__JID__'); 
  if(!r.ok) { document.getElementById('msg').textContent = 'Server Error ' + r.status; return; }
  const text = await r.text();
  let j;
  try { j = JSON.parse(text); } catch(e) { document.getElementById('msg').textContent = 'JSON Error: ' + text.substring(0, 50); return; }
  
  if (j.error) { document.getElementById('msg').textContent = j.error; return; }

  document.getElementById('msg').textContent = j.message || j.status;
  document.getElementById('fill').style.width = Math.round((j.frac||0)*100)+'%';
  document.getElementById('pct').innerText=Math.round((j.frac||0)*100)+'%';
  document.getElementById('mode').innerText = (j.mode==='ocr') ? 'Reading scanned pages' : ((j.mode==='text') ? 'Reading the text' : '');
 
 if(j.status === 'paused') {
   document.getElementById('btn-pause').style.display = 'none';
   document.getElementById('btn-resume').style.display = 'block';
   document.getElementById('msg').innerHTML = "<span style='color:#fbbf24;'>Paused</span> - " + (j.message||'');
 } else if (j.status === 'running' || j.status === 'queued') {
   document.getElementById('btn-pause').style.display = 'block';
   document.getElementById('btn-resume').style.display = 'none';
   document.getElementById('msg').innerHTML = j.message||'Processing...';
 } else {
   document.getElementById('btn-pause').style.display = 'none';
   document.getElementById('btn-resume').style.display = 'none';
   document.getElementById('msg').innerHTML = j.message||'Finished.';
 }

 let w = 0;
 let phase = j.phase;
 function hl(id) {
   let el = document.getElementById(id);
   if(el) { el.style.borderColor = 'var(--primary)'; el.style.color = 'var(--text)'; el.style.boxShadow = '0 0 8px var(--accent-glow)'; }
 }
 function rst(id) {
   let el = document.getElementById(id);
   if(el) { el.style.borderColor = 'var(--border)'; el.style.color = 'var(--text-muted)'; el.style.boxShadow = 'none'; }
 }
 if (phase === 'detect' || phase === 'extract' || phase === 'ocr') {
   w = 0; hl('dot-ocr'); rst('dot-tts'); rst('dot-mux');
 } else if (phase === 'tts') {
   w = 50; hl('dot-ocr'); hl('dot-tts'); rst('dot-mux');
 } else if (phase === 'mux' || phase === 'done') {
   w = 100; hl('dot-ocr'); hl('dot-tts'); hl('dot-mux');
 }
 document.getElementById('track-line').style.width = w + '%';

  if(j.status==='done'){
    let sub = '';
    document.getElementById('sub').textContent = sub;
    let mins = j.minutes || 0;
    let html = '<p class="ok" style="margin:0 0 16px; padding:12px 16px; border-radius:12px; display:flex; align-items:center; gap:8px; background:var(--primary-hover); color:var(--primary); border:1px solid var(--border);"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg> Finished ('+(mins/60).toFixed(1)+' h)</p>';
    html += '<audio id="player" src="/download/'+j.id+'" ontimeupdate="onT()" onloadedmetadata="onL()"></audio>';
    html += '<div style="background:var(--card); border:1px solid var(--border); border-radius:20px; padding:24px; margin:20px 0; box-shadow:inset 0 2px 10px rgba(0,0,0,0.2);">';
    html += '<div style="display:flex; align-items:center; justify-content:center; gap:32px; margin-bottom:20px;">';
    html += '<button onclick="skp(-15)" style="background:none; border:none; cursor:pointer; color:var(--text-muted); display:flex; align-items:center; justify-content:center; transition:color 0.2s; padding:8px;" onmouseover="this.style.color=&#39;var(--text)&#39;" onmouseout="this.style.color=&#39;var(--text-muted)&#39;">' + I_RW + '</button>';
    html += '<button id="playBtn" onclick="tglP()" style="background:linear-gradient(135deg, var(--primary), var(--accent)); border:none; color:white; width:64px; height:64px; border-radius:50%; cursor:pointer; display:flex; align-items:center; justify-content:center; box-shadow:0 8px 24px var(--accent-glow); padding-left:4px; transition:transform 0.2s;" onmouseover="this.style.transform=&#39;scale(1.05)&#39;" onmouseout="this.style.transform=&#39;scale(1)&#39;">' + I_PLAY + '</button>';
    html += '<button onclick="skp(15)" style="background:none; border:none; cursor:pointer; color:var(--text-muted); display:flex; align-items:center; justify-content:center; transition:color 0.2s; padding:8px;" onmouseover="this.style.color=&#39;var(--text)&#39;" onmouseout="this.style.color=&#39;var(--text-muted)&#39;">' + I_FF + '</button>';
    html += '</div><div style="display:flex; align-items:center; gap:16px;">';
    html += '<span id="cT" style="font-size:13px; font-weight:600; color:var(--text-muted); font-family:ui-monospace,monospace; min-width:44px; text-align:right;">0:00</span>';
    html += '<input type="range" id="pBar" value="0" max="100" step="0.1" oninput="onS(this.value)" style="flex:1; cursor:pointer; accent-color:var(--accent); height:6px; background:var(--border); border-radius:3px; outline:none; -webkit-appearance:none;">';
    html += '<span id="tT" style="font-size:13px; font-weight:600; color:var(--text-muted); font-family:ui-monospace,monospace; min-width:44px;">0:00</span>';
    html += '</div></div>';
    
    if (j.chapters_info && j.chapters_info.length > 0) {
        html += '<div class="ch-list" style="max-height:320px; overflow-y:auto; border:1px solid var(--border); border-radius:16px; background:var(--play-bg); margin-bottom:24px;">';
        j.chapters_info.forEach(function(ch) {
            let m = Math.floor(ch.start / 60), s = Math.floor(ch.start % 60);
            let timeStr = (m < 60) ? (m + ':' + (s<10?'0':'')+s) : (Math.floor(m/60) + ':' + ((m%60)<10?'0':'')+(m%60) + ':' + (s<10?'0':'')+s);
            html += '<div class="ch-row" style="padding:14px 18px; cursor:pointer; border-bottom:1px solid rgba(255,255,255,0.04); display:flex; gap:16px; align-items:center; transition:background 0.2s;" onclick="document.getElementById(&#39;player&#39;).currentTime=' + ch.start + '; document.getElementById(&#39;player&#39;).play(); document.getElementById(&#39;playBtn&#39;).innerHTML=I_PAUSE; document.getElementById(&#39;playBtn&#39;).style.paddingLeft=&#39;0&#39;;" onmouseover="this.style.background=&#39;rgba(255,255,255,0.05)&#39;" onmouseout="this.style.background=&#39;&#39;"><span style="color:var(--primary); font-family:ui-monospace,monospace; font-weight:700; font-size:13px; min-width:48px;">' + timeStr + '</span><span style="font-size:14px; color:#e2e8f0; font-weight:500; line-height:1.4;">' + ch.title + '</span></div>';
        });
        html += '</div>';
    }
    html += '<a class="dl" href="/download/'+j.id+'"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download M4B</a>';
    document.getElementById('result').innerHTML = html;
    return;
  }
 if(j.status==='error'){
   document.getElementById('result').innerHTML='<p class="err" style="margin:0 0 16px; padding:12px 16px; border-radius:12px;">'+(j.message||'Failed')+'</p>';
   return;
 }
 setTimeout(poll, 1500);
 } catch(e) {
   document.getElementById('msg').textContent = 'JS Error: ' + e.message;
 }
}
async function delJob(jid) {
  if (!confirm("Are you sure you want to stop and delete this job?")) return;
  await fetch("/api/job/" + jid + "/delete", {method: "POST"});
  window.location.href = "/";
}
async function togglePause(jid) {
  await fetch("/api/job/" + jid + "/pause", {method: "POST"});
}
async function toggleResume(jid) {
  await fetch("/api/job/" + jid + "/resume", {method: "POST"});
}
document.querySelector('select.theme-select').value = document.documentElement.className || 'theme-dark';
poll();
</script></body></html>"""
    return page.replace("__NAME__", html_name).replace("__CSS__", PAGE_CSS).replace("__JID__", j["id"])


@app.get("/download/{jid}")
def download(jid: str):
    j = jobs.get(jid)
    if not j or j.get("status") != "done":
        return HTMLResponse("Not ready or not found", status_code=404)
    out_m4b = os.path.join(j["dir"], j["base"] + ".m4b")
    if os.path.exists(out_m4b):
        return FileResponse(out_m4b, filename=j["base"] + ".m4b")
    return HTMLResponse("File missing", status_code=404)


@app.get("/ambiance/{name}")
def get_ambiance(name: str):
    path = os.path.join(BASE, "..", "ambiance", f"{name}.wav")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("Not found", 404)
