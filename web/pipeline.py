"""
Audiobook pipeline: epub -> (OCR if needed) -> clean text -> Kokoro TTS -> m4b.
Shared by the web app. All long steps take a progress callback:

    progress(phase: str, frac: float, message: str)
"""
import os, re, json, zipfile, shutil, subprocess, unicodedata
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import soundfile as sf
import pytesseract
from PIL import Image, ImageOps
from kokoro import KPipeline

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
SR = 24000

# Voices offered in the UI (label -> kokoro voice id). lang_code = id[0].
VOICES = {
    "Heart — American ♀ (warm, default)": "af_heart",
    "Bella — American ♀ (crisp)": "af_bella",
    "Nicole — American ♀ (soft)": "af_nicole",
    "Michael — American ♂": "am_michael",
    "Fenrir — American ♂ (deep)": "am_fenrir",
    "Emma — British ♀": "bf_emma",
    "George — British ♂": "bm_george",
}

# ---------------------------------------------------------------- ffmpeg
def find_ffmpeg():
    from shutil import which
    f = which("ffmpeg")
    if f:
        return f
    guess = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget."
        r"Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe")
    return guess if os.path.exists(guess) else "ffmpeg"

FFMPEG = find_ffmpeg()

# ---------------------------------------------------------------- detect
def detect_mode(epub_path):
    """Return 'ocr' (image-based, needs OCR) or 'text' (extractable text)."""
    from bs4 import BeautifulSoup
    z = zipfile.ZipFile(epub_path)
    names = z.namelist()
    docs = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]
    imgs = [n for n in names if re.search(r"\.(jpg|jpeg|png)$", n, re.I)]
    total_text = 0
    for d in docs:
        try:
            data = z.read(d).decode("utf-8", "ignore")
        except Exception:
            continue
        soup = BeautifulSoup(data, "html.parser")
        for t in soup(["style", "script", "head"]):   # drop CSS / page <title>
            t.decompose()
        total_text += len(re.sub(r"\s+", " ", soup.get_text(" ")).strip())
    avg = total_text / max(len(docs), 1)
    # image-based if there's barely any real body text, or images dominate
    if total_text < 2000 or (len(imgs) >= len(docs) * 0.5 and avg < 60):
        return "ocr"
    return "text"

# ---------------------------------------------------------------- OCR path
HEADER_RE = re.compile(r"Re:\s*Zero kara Hajimeru", re.I)
VOLUME_RE = re.compile(r"Web Novel Volume", re.I)
CHAPTER_RE = re.compile(r"(?:(?:Arc\s*(?P<arc>\d+)\s*)?Chapter\s*(?P<ch>\d+|[A-Za-z]+)|(?P<prologue>Prologue|Epilogue))(?:\s*[-–—=:]+\s*(?P<title>.*))?", re.I)
PAGENUM_RE = re.compile(r"^\d{1,4}$")
FOOTNOTE_RE = re.compile(r"^\d{1,2}\s+[A-Z]")
FNCONTENT_RE = re.compile(r"Engrish flip|Means\b.*\boriginally\b", re.I)
CREDIT_RE = re.compile(
    r"Light Novel Adaptation|found in Volume|Original Web Novel|Translation by|"
    r"Translations|TranslationChicken|Original Translation|Author|Illustrator|"
    r"Manifesto|Table of Contents|Other Volumes", re.I)
DOTLEADER_RE = re.compile(r"\.{5,}|\s\.\s\.\s\.")
TITLE_BAD = re.compile(r"Light Novel|found in|Original|Translation|Part\b|Mysterious World", re.I)


def _alpha_ratio(s):
    return sum(c.isalpha() or c.isspace() for c in s) / max(len(s), 1)


def _ocr_one(path):
    img = ImageOps.invert(Image.open(path).convert("L"))
    return os.path.basename(path), pytesseract.image_to_string(img, lang="eng")


def _clean_page(raw, state):
    if "Table of Contents" in raw or "Other Volumes" in raw or DOTLEADER_RE.search(raw):
        return []
    body, pending_title, in_footnotes = [], None, False
    for ln in raw.splitlines():
        s = ln.strip()
        if not s or in_footnotes:
            continue
        s = unicodedata.normalize("NFKC", s.replace("|", "I").replace("*", ""))
        m = CHAPTER_RE.search(s)
        if m:
            arc = m.group("arc") or ""
            ch = m.group("ch") or m.group("prologue") or ""
            title_str = m.group("title") or ""
            title = TITLE_BAD.split(title_str.strip())[0].strip(" -–—,")
            key = (arc, ch)
            if key != state["key"]:
                state["key"] = key
                disp = f"Arc {arc} " if arc else ""
                disp += f"Chapter {ch}" if m.group("ch") else ch
                if title: disp += f" - {title}"
                state["chapters"].append({"title": disp.strip(" -"), "lines": []})
                pending_title = True
            continue
        if HEADER_RE.search(s) or VOLUME_RE.search(s) or PAGENUM_RE.match(s):
            continue
        if FOOTNOTE_RE.match(s) or FNCONTENT_RE.search(s):
            in_footnotes = True
            continue
        if CREDIT_RE.search(s):
            pending_title = False
            continue
        if _alpha_ratio(s) < 0.55 or len(re.sub(r"[^A-Za-z]", "", s)) < 3:
            continue
        if pending_title and state["chapters"]:
            pending_title = False
            if len(s) <= 60 and not TITLE_BAD.search(s):
                state["chapters"][-1]["title"] += " " + s
                continue
        pending_title = False
        body.append(s)
    return body


def run_ocr(epub_path, work, progress):
    img_dir = os.path.join(work, "_images")
    os.makedirs(img_dir, exist_ok=True)
    z = zipfile.ZipFile(epub_path)
    img_names = sorted(n for n in z.namelist()
                       if re.search(r"\.(jpg|jpeg|png)$", n, re.I) and "images/" in n.lower())
    if not img_names:  # some epubs put images elsewhere
        img_names = sorted(n for n in z.namelist() if re.search(r"\.(jpg|jpeg|png)$", n, re.I))
    paths = []
    for n in img_names:
        dst = os.path.join(img_dir, os.path.basename(n))
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(z.read(n))
        paths.append(dst)

    total = len(paths)
    results = {}
    progress("ocr", 0.0, f"OCR 0/{total} pages")
    with ThreadPoolExecutor(max_workers=12) as ex:
        for i, (name, txt) in enumerate(ex.map(_ocr_one, paths), 1):
            results[name] = txt
            if i % 10 == 0 or i == total:
                progress("ocr", i / total, f"OCR {i}/{total} pages")

    ordered = [results[os.path.basename(p)] for p in paths]
    state = {"key": None, "chapters": []}
    for raw in ordered:
        body = _clean_page(raw, state)
        if body:
            if not state["chapters"]:
                state["chapters"].append({"title": "Chapter 1", "lines": []})
            state["chapters"][-1]["lines"].extend(body)
    chapters = [{"title": c["title"], "text": " ".join(c["lines"])}
                for c in state["chapters"] if c["lines"]]
    story = [c for c in chapters
             if re.match(r"(Arc\s*\d+\s*)?Chapter|Prologue|Epilogue", c["title"], re.I) and len(c["text"]) > 1500]
    return story or chapters  # fall back to all if no Arc/Chapter scheme

# ---------------------------------------------------------------- text path
def run_text(epub_path, work, progress):
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup
    book = epub.read_epub(epub_path, options={"ignore_ncx": True})
    chapters = []
    docs = list(book.get_items_of_type(ITEM_DOCUMENT))
    for i, item in enumerate(docs):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        h = soup.find(["h1", "h2", "title"])
        title = (h.get_text().strip() if h else f"Chapter {len(chapters)+1}")[:80]
        for t in soup(["style", "script", "head"]):
            t.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
        if len(text) < 200:
            continue
        chapters.append({"title": title or f"Chapter {len(chapters)+1}", "text": text})
        progress("extract", (i + 1) / len(docs), f"Reading text {i+1}/{len(docs)}")
    return chapters

# ---------------------------------------------------------------- cover
def get_cover(epub_path, work, mode):
    if mode == "ocr":
        p = os.path.join(work, "_images", "0001.jpg")
        return p if os.path.exists(p) else None
    z = zipfile.ZipFile(epub_path)
    imgs = [n for n in z.namelist() if re.search(r"\.(jpg|jpeg|png)$", n, re.I)]
    cands = [n for n in imgs if "cover" in n.lower()] or imgs[:1]
    if not cands:
        return None
    ext = os.path.splitext(cands[0])[1]
    dst = os.path.join(work, "cover" + ext)
    with open(dst, "wb") as f:
        f.write(z.read(cands[0]))
    return dst

# ---------------------------------------------------------------- TTS
_pipelines = {}

def _get_pipeline(lang):
    if lang not in _pipelines:
        _pipelines[lang] = KPipeline(lang_code=lang)
    return _pipelines[lang]


def synth_book(chapters, voice, work, progress, speed=1.0, marks_out=None):
    """Render each chapter to wav. If marks_out is a list, append one entry
    per chapter: a list of [char_end, t_end] pairs recording where each
    Kokoro chunk ends in the chapter text and in the chapter audio — the
    read-along reader uses these for precise text/audio sync. A chapter
    resumed from a cached wav gets None (no way to recover its timing).
    """
    n = len(chapters)
    progress("tts", 0.0, "Loading voice model…")
    pipe = _get_pipeline(voice[0])      # first call loads the model (a few sec)
    wav_dir = os.path.join(work, "_wav")
    os.makedirs(wav_dir, exist_ok=True)
    durations = []
    for i, c in enumerate(chapters):
        # report as the chapter STARTS so the bar never looks frozen
        progress("tts", i / n, f"Narrating chapter {i+1}/{n}: {c['title']}")
        out = os.path.join(wav_dir, f"ch{i:03d}.wav")
        ch_marks = None
        if not os.path.exists(out):
            parts, ch_marks, cursor, t = [], [], 0, 0.0
            for gs, _, a in pipe(c["text"], voice=voice, speed=speed):
                parts.append(a)
                t += len(a) / SR
                g = (gs or "").strip()
                idx = c["text"].find(g, cursor) if g else -1
                cursor = idx + len(g) if idx >= 0 else min(cursor + len(gs or ""), len(c["text"]))
                ch_marks.append([cursor, round(t, 3)])
            audio = np.concatenate(parts) if parts else np.zeros(SR, dtype="float32")
            sf.write(out, audio, SR)
        durations.append((c["title"], out, sf.info(out).frames / SR))
        if marks_out is not None:
            marks_out.append(ch_marks)
    return durations

# ---------------------------------------------------------------- mux
def mux_m4b(durations, work, cover, out_path, title, artist, bitrate="64k", ambiance=None, amb_vol=10):
    list_path = os.path.join(work, "_concat.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for _, wav, _ in durations:
            f.write(f"file '{wav.replace(os.sep, '/')}'\n")
    meta_path = os.path.join(work, "_chapters.txt")
    with open(meta_path, "w", encoding="utf-8") as m:
        m.write(f";FFMETADATA1\ntitle={title}\nartist={artist}\n")
        t = 0.0
        for ctitle, _, dur in durations:
            safe = re.sub(r"[=;#\\]", " ", ctitle)
            m.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(t*1000)}\n"
                    f"END={int((t+dur)*1000)}\ntitle={safe}\n")
            t += dur
            
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-i", meta_path]
    idx = 2
    
    if cover and os.path.exists(cover):
        cmd += ["-i", cover]
        has_cover = True
        cov_idx = idx
        idx += 1
    else:
        has_cover = False

    if ambiance and os.path.exists(ambiance):
        cmd += ["-stream_loop", "-1", "-i", ambiance]
        has_amb = True
        amb_idx = idx
        idx += 1
    else:
        has_amb = False

    if has_amb:
        vol = max(0.0, min(float(amb_vol) / 100.0, 1.0))
        cmd += ["-filter_complex", f"[0:a][{amb_idx}:a]amix=inputs=2:duration=first:dropout_transition=2:weights=1 {vol:.2f}[a]", "-map", "[a]"]
    else:
        cmd += ["-map", "0:a"]
        
    if has_cover:
        cmd += ["-map", f"{cov_idx}:v", "-disposition:v", "attached_pic"]

    cmd += ["-map_metadata", "1", "-c:a", "aac", "-b:a", bitrate, "-c:v", "copy", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Add Nero chapters using Mutagen for Apple Books compatibility
    try:
        from mutagen.mp4 import MP4, Chapter
        audio = MP4(out_path)
        chaps = []
        t = 0.0
        for ctitle, _, dur in durations:
            safe = re.sub(r"[=;#\\]", " ", ctitle)
            chaps.append(Chapter(t, safe))
            t += dur
        audio.chapters = chaps
        audio.save()
    except Exception as e:
        print(f"Warning: Failed to add mutagen chapters: {e}")
        
    return out_path
