import zipfile, re, sys

path = r"A:\Cowork\Ebooks\Re-Zero-Web-Novel-Vol-23.epub"
z = zipfile.ZipFile(path)
names = z.namelist()
imgs = [n for n in names if re.search(r"\.(jpg|jpeg|png|gif|webp|svg)$", n, re.I)]
xhtml = [n for n in names if n.endswith(".xhtml") or n.endswith(".html")]

print("total entries:", len(names))
print("images:", len(imgs))
print("xhtml/html docs:", len(xhtml))

# total image bytes vs text bytes
img_bytes = sum(z.getinfo(n).file_size for n in imgs)
print("image bytes:", round(img_bytes/1024/1024, 1), "MB")

# Inspect a middle page's raw content
mid = [n for n in xhtml if "0100" in n or "0050" in n]
sample = (mid[:1] or xhtml[len(xhtml)//2:len(xhtml)//2+1])
for s in sample:
    data = z.read(s).decode("utf-8", "ignore")
    # strip tags to see actual text
    text = re.sub(r"<[^>]+>", "", data)
    text = re.sub(r"\s+", " ", text).strip()
    print("\n--- RAW", s, "(", len(data), "bytes ) ---")
    print(data[:1500])
    print("\n--- VISIBLE TEXT (", len(text), "chars ) ---")
    print(repr(text[:500]))
