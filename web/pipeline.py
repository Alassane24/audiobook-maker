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
    """Return 'ocr' (image-based, needs OCR) or 'text' (extractable text) or 'pdf'."""
    if epub_path.lower().endswith(".pdf"):
        return "pdf"
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
PAGENUM_RE = re.compile(r"^(?:-?\s*(?:page\s*)?\d{1,4}\s*-?:?)$", re.I)
# Speaker labels in these scans are little portrait icons; OCR mangles
# them into digits ("222:" before a quote, regardless of who speaks).
# Normalize to the web-novel's unknown-speaker form so the reader can
# still break dialogue onto its own line.
BAD_SPEAKER_RE = re.compile(r"(?<![\w])\d{1,4}:\s*(?=[“”\"'\[])")
FOOTNOTE_RE = re.compile(r"^\d{1,2}\s+[A-Z]")
FNCONTENT_RE = re.compile(r"Engrish flip|Means\b.*\boriginally\b", re.I)
CREDIT_RE = re.compile(
    r"Light Novel Adaptation|found in Volume|Original Web Novel|Translation by|"
    r"Translations|TranslationChicken|Original Translation|Author|Illustrator|"
    r"Manifesto|Table of Contents|Other Volumes", re.I)
DOTLEADER_RE = re.compile(r"\.{5,}|\s\.\s\.\s\.")
TITLE_BAD = re.compile(r"Light Novel|found in|Original|Translation|Part\b|Mysterious World", re.I)
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\uFAFF\uFF66-\uFF9F]+")
OCR_FIXES = [
    (re.compile(r"\bT'm\b"), "I'm"),
    (re.compile(r"\bT'd\b"), "I'd"),
    (re.compile(r"\bT'll\b"), "I'll"),
    (re.compile(r"\bT've\b"), "I've"),
    (re.compile(r"\bTf\b"), "If"),
    (re.compile(r"\bTt\b"), "It"),
    (re.compile(r"\bTs\b"), "Is"),
    (re.compile(r"\bTn\b"), "In"),
    (re.compile(r"\bTnto\b"), "Into"),
    (re.compile(r"\bTts\b"), "Its"),
    (re.compile(r"\bTtself\b"), "Itself"),
    (re.compile(r"\bTM\b"), "I'm"),
    (re.compile(r"\bTF\b"), "If"),
    (re.compile(r"(?<!-)\bT\b(?!-)"), "I"),
]


def _alpha_ratio(s):
    return sum(c.isalpha() or c.isspace() for c in s) / max(len(s), 1)


# Tesseract language data. The repo does not ship tessdata/ (it is fetched, not
# authored), so use a copy beside the repo when one is there and otherwise let
# Tesseract fall back to its own install. AUDIOBOOK_TESSDATA overrides both.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESSDATA_DIR = os.environ.get("AUDIOBOOK_TESSDATA") or os.path.join(_REPO_ROOT, "tessdata")
_TESS_CONFIG = f'--tessdata-dir "{TESSDATA_DIR}"' if os.path.isdir(TESSDATA_DIR) else ""


def _ocr_one(path):
    img = ImageOps.invert(Image.open(path).convert("L"))
    return os.path.basename(path), pytesseract.image_to_string(img, lang="eng+jpn", config=_TESS_CONFIG)


def _clean_page(raw, state):
    if "Table of Contents" in raw or "Other Volumes" in raw or DOTLEADER_RE.search(raw):
        return []
    body, pending_title, in_footnotes = [], None, False
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for i, s in enumerate(lines):
        if in_footnotes:
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
        if HEADER_RE.search(s) or VOLUME_RE.search(s):
            continue
        if PAGENUM_RE.match(s):
            if i == 0 or i == len(lines) - 1:
                continue
        if FOOTNOTE_RE.match(s) or FNCONTENT_RE.search(s):
            in_footnotes = True
            continue
        if CREDIT_RE.search(s):
            pending_title = False
            continue
        for pattern, replacement in OCR_FIXES:
            s = pattern.sub(replacement, s)
        s = JAPANESE_RE.sub(" [Japanese text] ", s)
        if _alpha_ratio(s) < 0.55 or len(re.sub(r"[^A-Za-z]", "", s)) < 3:
            continue
        s = BAD_SPEAKER_RE.sub("???: ", s)
        if pending_title and state["chapters"]:
            pending_title = False
            # A wrapped title fragment never ends in sentence punctuation;
            # a first prose line usually does — don't glue prose onto titles.
            if len(s) <= 60 and not TITLE_BAD.search(s) and not re.search(r"[.!?…”\"]$", s):
                state["chapters"][-1]["title"] += " " + s
                continue
        pending_title = False
        body.append(s)
    return body


def _is_art(path):
    """Among pages that OCR to nothing: artwork vs blank. Calibrated on
    the Re:Zero scans (white-on-black): blank/junk pages sit at stddev
    6-19, illustrations at 32+. Text pages never reach this check."""
    try:
        from PIL import ImageStat
        img = Image.open(path).convert("L")
        img.thumbnail((400, 400))
        return ImageStat.Stat(img).stddev[0] > 22
    except Exception:
        return False


def _chapter_char_len(ch):
    """Length of the chapter text as it will exist after ' '.join(lines)."""
    lines = ch["lines"]
    return sum(len(l) for l in lines) + max(0, len(lines) - 1)


def run_ocr(epub_path, work, progress):
    img_dir = os.path.join(work, "_images")
    os.makedirs(img_dir, exist_ok=True)
    z = zipfile.ZipFile(epub_path)
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
    
    img_names = sorted((n for n in z.namelist()
                       if re.search(r"\.(jpg|jpeg|png)$", n, re.I) and "images/" in n.lower()), key=natural_sort_key)
    if not img_names:  # some epubs put images elsewhere
        img_names = sorted((n for n in z.namelist() if re.search(r"\.(jpg|jpeg|png)$", n, re.I)), key=natural_sort_key)
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
    pending_art = []   # illustration pages seen before the first chapter
    for path, raw in zip(paths, ordered):
        body = _clean_page(raw, state)
        if body:
            if not state["chapters"]:
                state["chapters"].append({"title": "Chapter 1", "lines": [], "images": []})
            cur = state["chapters"][-1]
            cur.setdefault("images", [])
            if pending_art:
                cur["images"].extend({"char": 0, "file": f} for f in pending_art)
                pending_art = []
            cur["lines"].extend(body)
        elif len(raw.strip()) < 120 and _is_art(path):
            # A page with no extractable text but real pixel content is an
            # illustration; anchor it where the story currently stands.
            if state["chapters"]:
                cur = state["chapters"][-1]
                cur.setdefault("images", []).append(
                    {"char": _chapter_char_len(cur), "file": os.path.basename(path)})
            else:
                pending_art.append(os.path.basename(path))
    chapters = [{"title": c["title"], "text": " ".join(c["lines"]), "images": c.get("images", [])}
                for c in state["chapters"] if c["lines"]]
    for c in chapters:
        c["text"] = re.sub(r"(?:\[Japanese text\]\s*)+", "[Japanese text] ", c["text"])
    story = [c for c in chapters
             if re.match(r"(Arc\s*\d+\s*)?Chapter|Prologue|Epilogue", c["title"], re.I) and len(c["text"]) > 1500]
    if story:
        # Art belonging to dropped chapters re-anchors to the nearest kept
        # chapter before it (front-matter art lands at the start of the
        # first kept chapter) so nothing is lost or teleported.
        kept = {id(c) for c in story}
        last_kept = None
        for c in chapters:
            if id(c) in kept:
                last_kept = c
            elif c.get("images"):
                target = last_kept or story[0]
                anchor = len(target["text"]) if last_kept else 0
                target.setdefault("images", []).extend(
                    {"char": anchor, "file": img["file"]} for img in c["images"])
    return story or chapters  # fall back to all if no Arc/Chapter scheme

# ---------------------------------------------------------------- pdf path
def run_pdf(pdf_path, work, progress):
    import fitz
    img_dir = os.path.join(work, "_images")
    os.makedirs(img_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    total = len(doc)
    paths = []
    progress("ocr", 0.0, f"Extracting {total} PDF pages...")
    for i in range(total):
        page = doc.load_page(i)
        # High resolution: 300 DPI for better OCR accuracy
        pix = page.get_pixmap(dpi=300)
        dst = os.path.join(img_dir, f"page_{i:04d}.png")
        pix.save(dst)
        paths.append(dst)
        if i % 10 == 0:
            progress("ocr", i / total * 0.1, f"Extracting PDF {i}/{total}")

    results = {}
    progress("ocr", 0.1, f"OCR 0/{total} pages")
    with ThreadPoolExecutor(max_workers=12) as ex:
        for i, (name, txt) in enumerate(ex.map(_ocr_one, paths), 1):
            results[name] = txt
            if i % 10 == 0 or i == total:
                progress("ocr", 0.1 + (i / total) * 0.9, f"OCR {i}/{total} pages")

    ordered = [results[os.path.basename(p)] for p in paths]
    state = {"key": None, "chapters": []}
    pending_art = []
    for path, raw in zip(paths, ordered):
        body = _clean_page(raw, state)
        if body:
            if not state["chapters"]:
                state["chapters"].append({"title": "Chapter 1", "lines": [], "images": []})
            cur = state["chapters"][-1]
            cur.setdefault("images", [])
            if pending_art:
                cur["images"].extend({"char": 0, "file": f} for f in pending_art)
                pending_art = []
            cur["lines"].extend(body)
        elif len(raw.strip()) < 120 and _is_art(path):
            if state["chapters"]:
                cur = state["chapters"][-1]
                cur.setdefault("images", []).append(
                    {"char": _chapter_char_len(cur), "file": os.path.basename(path)})
            else:
                pending_art.append(os.path.basename(path))
    chapters = [{"title": c["title"], "text": " ".join(c["lines"]), "images": c.get("images", [])}
                for c in state["chapters"] if c["lines"]]
    for c in chapters:
        c["text"] = re.sub(r"(?:\[Japanese text\]\s*)+", "[Japanese text] ", c["text"])
    story = [c for c in chapters
             if re.match(r"(Arc\s*\d+\s*)?Chapter|Prologue|Epilogue", c["title"], re.I) and len(c["text"]) > 1500]
    if story:
        kept = {id(c) for c in story}
        last_kept = None
        for c in chapters:
            if id(c) in kept:
                last_kept = c
            elif c.get("images"):
                target = last_kept or story[0]
                anchor = len(target["text"]) if last_kept else 0
                target.setdefault("images", []).extend(
                    {"char": anchor, "file": img["file"]} for img in c["images"])
    return story or chapters

# ---------------------------------------------------------------- text path
def run_text(epub_path, work, progress):
    import posixpath
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup, NavigableString
    book = epub.read_epub(epub_path, options={"ignore_ncx": True})
    z = zipfile.ZipFile(epub_path)
    zip_names = {n.lower(): n for n in z.namelist()}
    img_dir = os.path.join(work, "_images")
    chapters = []
    pending_imgs = []   # art from image-only docs, carried to the next chapter
    docs = []
    for item_id, _ in book.spine:
        item = book.get_item_with_id(item_id)
        if item and item.get_type() == ITEM_DOCUMENT:
            docs.append(item)
    for i, item in enumerate(docs):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        h = soup.find(["h1", "h2", "title"])
        title = (h.get_text().strip() if h else f"Chapter {len(chapters)+1}")[:80]
        for t in soup(["style", "script", "head"]):
            t.decompose()

        # Swap each inline image for a zero-width sentinel, squash the text
        # exactly as before, then read the sentinel positions back out —
        # that gives the image's true character anchor in the final text.
        img_srcs = []
        for k, tag in enumerate(soup.find_all(["img", "image"])):
            src = tag.get("src") or tag.get("href") or tag.get("xlink:href") or ""
            tag.replace_with(NavigableString(f"\x00{k}\x00"))
            img_srcs.append(src)
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()

        # Resolve offsets left-to-right while removing sentinels.
        images = []
        out, pos = [], 0
        for m in re.finditer(r"\x00(\d+)\x00", text):
            out.append(text[pos:m.start()])
            images.append({"char": sum(len(s) for s in out), "k": int(m.group(1))})
            pos = m.end()
        out.append(text[pos:])
        text = "".join(out)

        ch_images = []
        for img in images:
            src = img_srcs[img["k"]]
            if not src:
                continue
            try:
                rel = posixpath.normpath(posixpath.join(posixpath.dirname(item.get_name()), src))
                real = zip_names.get(rel.lower()) or zip_names.get(src.lstrip("./").lower())
                if not real:
                    continue
                os.makedirs(img_dir, exist_ok=True)
                fname = f"d{i:03d}_{os.path.basename(real)}"
                dst = os.path.join(img_dir, fname)
                if not os.path.exists(dst):
                    with open(dst, "wb") as f:
                        f.write(z.read(real))
                ch_images.append({"char": img["char"], "file": fname})
            except Exception:
                continue

        if len(text) < 200:
            # Insert-art pages ship as image-only docs in text epubs; the
            # doc is skipped but its art carries to the next real chapter.
            pending_imgs.extend({"char": 0, "file": im["file"]} for im in ch_images)
            continue

        chapters.append({"title": title or f"Chapter {len(chapters)+1}", "text": text,
                         "images": pending_imgs + ch_images})
        pending_imgs = []
        progress("extract", (i + 1) / len(docs), f"Reading text {i+1}/{len(docs)}")
    if pending_imgs and chapters:
        # Trailing art (after the last chapter) pins to the end of the book.
        last = chapters[-1]
        last["images"] = last.get("images", []) + [
            {"char": len(last["text"]), "file": im["file"]} for im in pending_imgs]
    return chapters

# ---------------------------------------------------------------- cover
def get_cover(epub_path, work, mode):
    if mode == "pdf":
        p = os.path.join(work, "_images", "page_0000.png")
        return p if os.path.exists(p) else None
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
