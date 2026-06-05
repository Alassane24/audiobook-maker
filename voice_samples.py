"""Generate the same passage across several Kokoro voices for A/B comparison."""
import os
import soundfile as sf
from kokoro import KPipeline

OUT = r"A:\Cowork\audiobooks\samples\voices"
os.makedirs(OUT, exist_ok=True)

# Narration + a line of dialogue, to test both reading styles.
TEXT = (
    "It is a truth universally acknowledged, that a single man in possession "
    "of a good fortune, must be in want of a wife. However little known the "
    "feelings or views of such a man may be on his first entering a neighbourhood, "
    "this truth is so well fixed in the minds of the surrounding families. "
    "\"My dear Mr. Bennet,\" said his lady to him one day, "
    "\"have you heard that Netherfield Park is let at last?\""
)

# voice name -> lang_code ('a' = American English, 'b' = British English)
VOICES = {
    "af_heart":   "a",  # warm American female (the baseline you heard)
    "af_bella":   "a",  # American female, often rated highest quality
    "af_nicole":  "a",  # American female, softer / breathier
    "am_michael": "a",  # American male, neutral narrator
    "am_fenrir":  "a",  # American male, deeper
    "bf_emma":    "b",  # British female
    "bm_george":  "b",  # British male
}

# One pipeline per lang_code (reused across voices).
pipelines = {}
for voice, lang in VOICES.items():
    if lang not in pipelines:
        pipelines[lang] = KPipeline(lang_code=lang)
    pipe = pipelines[lang]
    chunks = [audio for _, _, audio in pipe(TEXT, voice=voice)]
    import numpy as np
    audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    path = os.path.join(OUT, f"{voice}.wav")
    sf.write(path, audio, 24000)
    print(f"wrote {path}  ({len(audio)/24000:.1f}s)")

print("DONE")
