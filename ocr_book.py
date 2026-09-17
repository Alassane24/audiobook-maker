"""
OCR an image-based epub into clean, chapter-split text ready for TTS.

Usage:
    python ocr_book.py <epub_path> <work_dir>

Outputs into <work_dir>:
    _images/         extracted page images
    raw_text.txt     unmodified OCR dump (for debugging)
    clean_text.txt   cleaned, header/footnote-stripped text
    chapters.json    [{"title": ..., "text": ...}, ...]
"""
import sys, os, re, json, zipfile, unicodedata
from concurrent.futures import ProcessPoolExecutor

CACHE = None  # set in main()

import pytesseract
from PIL import Image, ImageOps

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

EPUB = sys.argv[1]
WORK = sys.argv[2]
IMG_DIR = os.path.join(WORK, "_images")
os.makedirs(IMG_DIR, exist_ok=True)


def extract_images(epub_path, out_dir):
    z = zipfile.ZipFile(epub_path)
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
    
    imgs = sorted((n for n in z.namelist()
                  if re.search(r"\.(jpg|jpeg|png)$", n, re.I) and "images/" in n), key=natural_sort_key)
    paths = []
    for n in imgs:
        fname = os.path.basename(n)
        dst = os.path.join(out_dir, fname)
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(z.read(n))
        paths.append(dst)
    return paths


def ocr_one(path):
    img = Image.open(path).convert("L")
    img = ImageOps.invert(img)          # white-on-black -> black-on-white
    txt = pytesseract.image_to_string(img, lang="eng")
    return os.path.basename(path), txt


# ---- cleaning ----------------------------------------------------------

HEADER_RE = re.compile(r"Re:\s*Zero kara Hajimeru", re.I)
VOLUME_RE = re.compile(r"Web Novel Volume", re.I)
CHAPTER_RE = re.compile(r"Arc\s*(\d+)\s*Chapter\s*(\d+)\s*[-–—=]+\s*(.*)", re.I)
PAGENUM_RE = re.compile(r"^(?:-?\s*(?:page\s*)?\d{1,4}\s*-?:?)$", re.I)
FOOTNOTE_RE = re.compile(r"^\d{1,2}\s+[A-Z]")       # "2 Engrish flip...", bottom-of-page notes
# footnote content signature (catches notes whose leading number OCR'd as garbage)
FNCONTENT_RE = re.compile(r"Engrish flip|Means\b.*\boriginally\b", re.I)
# translator credit / chapter-mapping blurbs that leak into the body
CREDIT_RE = re.compile(
    r"Light Novel Adaptation|found in Volume|Original Web Novel|"
    r"Translation by|Translations|TranslationChicken|Original Translation|"
    r"Author|Illustrator|Manifesto|Table of Contents|Other Volumes",
    re.I,
)
DOTLEADER_RE = re.compile(r"\.{5,}|\s\.\s\.\s\.")   # TOC dotted leaders
TITLE_BAD = re.compile(
    r"Light Novel|found in|Original|Translation|Part\b|Mysterious World", re.I
)


def alpha_ratio(s):
    letters = sum(c.isalpha() or c.isspace() for c in s)
    return letters / max(len(s), 1)


def clean_page(raw, state):
    """Return list of body lines for this page; update chapter state in place."""
    # Skip whole page if it's a table-of-contents / index page: those carry
    # fake "Arc 6 Chapter NN" lines that scramble chapter detection.
    if "Table of Contents" in raw or "Other Volumes" in raw or DOTLEADER_RE.search(raw):
        return []

    body = []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    pending_title = None
    in_footnotes = False        # once notes begin, the rest of the page is notes
    for i, s in enumerate(lines):
        if in_footnotes:
            continue
        # normalize the I/| OCR error and footnote markers
        s = s.replace("|", "I").replace("*", "")
        s = unicodedata.normalize("NFKC", s)

        m = CHAPTER_RE.search(s)
        if m:
            arc, ch, title = m.group(1), m.group(2), m.group(3).strip()
            # if the title tail is actually a credit blurb, cut it off
            title = TITLE_BAD.split(title)[0].strip(" -–—,")
            key = (arc, ch)
            if key != state["key"]:
                state["key"] = key
                state["chapters"].append(
                    {"title": f"Arc {arc} Chapter {ch} - {title}".strip(" -"),
                     "lines": []}
                )
                pending_title = True   # next line *might* be a wrapped title
            continue
        if HEADER_RE.search(s) or VOLUME_RE.search(s):
            continue
        if PAGENUM_RE.match(s):
            if i == 0 or i == len(lines) - 1:
                continue
        if FOOTNOTE_RE.match(s) or FNCONTENT_RE.search(s):
            in_footnotes = True       # drop this note and everything after it
            continue
        if CREDIT_RE.search(s):           # translator notes / mapping blurbs
            pending_title = False
            continue
        # drop garbage lines (mostly non-latin: japanese furigana, "2? & 272;")
        if alpha_ratio(s) < 0.55 or len(re.sub(r"[^A-Za-z]", "", s)) < 3:
            continue
        # wrapped chapter title: only if short and clearly not body/credit text
        if pending_title and state["chapters"]:
            pending_title = False
            if len(s) <= 60 and not TITLE_BAD.search(s):
                state["chapters"][-1]["title"] += " " + s
                continue
        pending_title = False
        body.append(s)
    return body


def main():
    print("Extracting images...", flush=True)
    paths = extract_images(EPUB, IMG_DIR)
    cache_path = os.path.join(WORK, "ocr_cache.json")

    if os.path.exists(cache_path):
        results = json.load(open(cache_path, encoding="utf-8"))
        if all(os.path.basename(p) in results for p in paths):
            print("Using cached OCR results.", flush=True)
        else:
            results = None
    else:
        results = None

    if results is None:
        print(f"{len(paths)} pages. Running OCR across CPU cores...", flush=True)
        results = {}
        with ProcessPoolExecutor(max_workers=12) as ex:
            for i, (name, txt) in enumerate(ex.map(ocr_one, paths), 1):
                results[name] = txt
                if i % 25 == 0:
                    print(f"  OCR {i}/{len(paths)}", flush=True)
        json.dump(results, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)

    ordered = [results[os.path.basename(p)] for p in paths]
    with open(os.path.join(WORK, "raw_text.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(ordered))

    state = {"key": None, "chapters": []}
    # fallback single chapter if no Arc/Chapter headers ever match
    for raw in ordered:
        if not state["chapters"]:
            # ensure a chapter exists before headerless body shows up
            pass
        body = clean_page(raw, state)
        if body:
            if not state["chapters"]:
                state["chapters"].append({"title": "Volume 23", "lines": []})
            state["chapters"][-1]["lines"].extend(body)

    chapters = [{"title": c["title"], "text": " ".join(c["lines"])}
                for c in state["chapters"] if c["lines"]]
    # keep only real story chapters (have an "Arc N Chapter N" title with body);
    # drops the translator front-matter / manifesto.
    chapters = [c for c in chapters
                if re.match(r"Arc\s*\d+\s*Chapter", c["title"], re.I)
                and len(c["text"]) > 1500]

    with open(os.path.join(WORK, "clean_text.txt"), "w", encoding="utf-8") as f:
        for c in chapters:
            f.write(f"\n\n### {c['title']}\n\n{c['text']}\n")
    with open(os.path.join(WORK, "chapters.json"), "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=1)

    print(f"\nDONE. {len(chapters)} chapters detected:")
    for c in chapters:
        print(f"  - {c['title']}  ({len(c['text'])} chars)")


if __name__ == "__main__":
    main()
