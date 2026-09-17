import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"))
import paths

import pytesseract
from PIL import Image, ImageOps

# Point at the Tesseract binary (winget install location)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

for page in ["page0010.jpg", "page0050.jpg"]:
    path = os.path.join(paths.SAMPLES_DIR, page)
    img = Image.open(path).convert("L")        # grayscale
    img = ImageOps.invert(img)                 # white-on-black -> black-on-white
    text = pytesseract.image_to_string(img, lang="eng")
    print(f"\n========== {page} ==========")
    print(text.strip())
