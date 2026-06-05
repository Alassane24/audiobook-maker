"""
Turn chapters.json into an audiobook with Kokoro.

    python tts_book.py <work_dir> <voice> [--sample]

--sample : synthesize only the first ~2500 chars of chapter 2 to a quick mp3
           (for validating text/voice before the full render)

Full mode produces <work_dir>/<basename>.m4b  (AAC, chapter markers, cover).
Requires ffmpeg on PATH.
"""
import sys, os, re, json, subprocess
import numpy as np
import soundfile as sf
from kokoro import KPipeline

WORK = sys.argv[1]
VOICE = sys.argv[2]
SAMPLE = "--sample" in sys.argv
SR = 24000

chapters = json.load(open(os.path.join(WORK, "chapters.json"), encoding="utf-8"))
pipe = KPipeline(lang_code="a")          # af_* voices are American English


def synth(text):
    chunks = [audio for _, _, audio in pipe(text, voice=VOICE)]
    return np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")


if SAMPLE:
    text = chapters[1]["text"][:2500]
    print("Sampling:", chapters[1]["title"])
    audio = synth(text)
    wav = os.path.join(WORK, "sample.wav")
    mp3 = os.path.join(WORK, "sample.mp3")
    sf.write(wav, audio, SR)
    subprocess.run(["ffmpeg", "-y", "-i", wav, "-b:a", "96k", mp3],
                   check=True, capture_output=True)
    os.remove(wav)
    print("WROTE", mp3)
    sys.exit(0)

# ---- full render -------------------------------------------------------
wav_dir = os.path.join(WORK, "_wav")
os.makedirs(wav_dir, exist_ok=True)

durations = []
list_path = os.path.join(WORK, "_concat.txt")
with open(list_path, "w", encoding="utf-8") as lst:
    for i, c in enumerate(chapters):
        out = os.path.join(wav_dir, f"ch{i:02d}.wav")
        if not os.path.exists(out):
            audio = synth(c["text"])
            sf.write(out, audio, SR)
        dur = sf.info(out).frames / SR
        durations.append((c["title"], dur))
        lst.write(f"file '{out.replace(chr(92), '/')}'\n")
        print(f"  [{i+1}/{len(chapters)}] {c['title']}  ({dur/60:.1f} min)", flush=True)

# ffmetadata with chapter markers
meta_path = os.path.join(WORK, "_chapters.txt")
with open(meta_path, "w", encoding="utf-8") as m:
    m.write(";FFMETADATA1\ntitle=Re:Zero Web Novel Vol 23\nartist=Tappei Nagatsuki\n")
    t = 0.0
    for title, dur in durations:
        start = int(t * 1000)
        end = int((t + dur) * 1000)
        safe = re.sub(r"[=;#\\]", " ", title)
        m.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle={safe}\n")
        t += dur

base = "Re-Zero-Web-Novel-Vol-23"
cover = os.path.join(WORK, "_images", "0001.jpg")
out_m4b = os.path.join(WORK, base + ".m4b")

cmd = ["ffmpeg", "-y",
       "-f", "concat", "-safe", "0", "-i", list_path,
       "-i", meta_path]
if os.path.exists(cover):
    cmd += ["-i", cover, "-map", "0:a", "-map", "2:v", "-disposition:v", "attached_pic"]
else:
    cmd += ["-map", "0:a"]
cmd += ["-map_metadata", "1",
        "-c:a", "aac", "-b:a", "64k",      # mono narration: 64k is plenty
        "-c:v", "copy",
        out_m4b]
print("Muxing M4B (AAC)...", flush=True)
subprocess.run(cmd, check=True, capture_output=True)
print("WROTE", out_m4b)
