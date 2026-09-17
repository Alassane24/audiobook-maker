import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"))
import paths

import os
import json
from mutagen.mp4 import MP4, Chapter

JOBS_DIR = paths.JOBS_DIR
TRANSFER_DIR = paths.TRANSFER_DIR

for jid in os.listdir(JOBS_DIR):
    jpath = os.path.join(JOBS_DIR, jid)
    st = os.path.join(jpath, "status.json")
    if os.path.exists(st):
        with open(st, "r", encoding="utf-8") as f:
            j = json.load(f)
        base = j.get("base")
        if not base: continue
        out_m4b = os.path.join(TRANSFER_DIR, base + ".m4b")
        ch_path = os.path.join(jpath, "_chapters.txt")
        if os.path.exists(out_m4b) and os.path.exists(ch_path):
            chaps = []
            title = ""
            start = 0.0
            with open(ch_path, "r", encoding="utf-8") as cf:
                for line in cf.read().splitlines():
                    if line.startswith("START="):
                        start = int(line.split("=")[1]) / 1000.0
                    elif line.startswith("title="):
                        title = line.split("=", 1)[1]
                        if title and title != base:
                            chaps.append(Chapter(start, title))
            if chaps:
                print(f"Patching {base}.m4b with {len(chaps)} chapters...")
                try:
                    audio = MP4(out_m4b)
                    audio.chapters = chaps
                    audio.save()
                    print(f"Success for {base}.m4b")
                except Exception as e:
                    print(f"Error patching {base}.m4b: {e}")
