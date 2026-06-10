// Read-along engine: turns chapter text + audio timing into pages, and
// maps audio time <-> character position.
//
// Sync precision has two tiers:
//   - Books rendered after the timing feature: timing.json holds
//     [charEnd, tEnd] marks per Kokoro chunk (a sentence or two) —
//     interpolating inside a chunk is accurate to ~a second.
//   - Older books: no marks, so position is estimated proportionally by
//     character offset within the chapter. Kokoro's pace is uniform
//     enough that this holds to roughly a sentence at page granularity.

export interface ReaderChapter {
  title: string;
  text: string;
}

export type ChapterMarks = [number, number][] | null; // [charEnd, tEnd] pairs

export interface BookText {
  chapters: ReaderChapter[];
  timing: ChapterMarks[] | null;
}

export interface Sentence {
  text: string;
  start: number; // char offset, chapter-local
}

export interface Page {
  chapter: number;
  charStart: number;
  charEnd: number;
  paras: Sentence[][];
}

export function splitSentences(text: string): Sentence[] {
  const out: Sentence[] = [];
  // A sentence = text up to terminal punctuation (plus closing quotes),
  // or the trailing remainder. Abbreviation false-splits are harmless at
  // this granularity.
  const re = /[^.!?…]+[.!?…]+[”’"')\]]*\s*|[^.!?…]+\s*$/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m[0].trim()) out.push({ text: m[0], start: m.index });
    if (m.index === re.lastIndex) re.lastIndex++; // safety against zero-width stalls
  }
  return out;
}

// Group sentences into pages of ~charsPerPage, breaking only between
// sentences. Within a page, sentences cluster into faux paragraphs of 4
// purely for visual rhythm (the pipeline's cleaned text is one long line;
// original paragraph breaks don't survive OCR).
export function buildPages(chapters: ReaderChapter[], charsPerPage: number): Page[] {
  const pages: Page[] = [];
  const budget = Math.max(280, charsPerPage);
  chapters.forEach((ch, ci) => {
    const sentences = splitSentences(ch.text);
    let cur: Sentence[] = [];
    let curChars = 0;
    let pageStart = 0;

    const flush = (end: number) => {
      if (!cur.length) return;
      const paras: Sentence[][] = [];
      for (let i = 0; i < cur.length; i += 4) paras.push(cur.slice(i, i + 4));
      pages.push({ chapter: ci, charStart: pageStart, charEnd: end, paras });
      cur = [];
      curChars = 0;
    };

    for (const s of sentences) {
      if (curChars > 0 && curChars + s.text.length > budget) flush(s.start);
      if (cur.length === 0) pageStart = s.start;
      cur.push(s);
      curChars += s.text.length;
    }
    flush(ch.text.length);
  });
  return pages;
}

function bisectMarks(marks: [number, number][], value: number, key: 0 | 1): number {
  let lo = 0, hi = marks.length - 1, idx = marks.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (marks[mid][key] >= value) { idx = mid; hi = mid - 1; }
    else lo = mid + 1;
  }
  return idx;
}

const clamp01 = (f: number) => Math.max(0, Math.min(1, f));

// Audio offset within a chapter -> character offset in its text.
export function charAtTime(text: string, marks: ChapterMarks, tIn: number, chapterDur: number): number {
  if (marks && marks.length) {
    const i = bisectMarks(marks, tIn, 1);
    const [cEnd, tEnd] = marks[i];
    const cPrev = i > 0 ? marks[i - 1][0] : 0;
    const tPrev = i > 0 ? marks[i - 1][1] : 0;
    const f = tEnd > tPrev ? clamp01((tIn - tPrev) / (tEnd - tPrev)) : 1;
    return Math.round(cPrev + f * (cEnd - cPrev));
  }
  if (chapterDur <= 0) return 0;
  return Math.round(text.length * clamp01(tIn / chapterDur));
}

// Character offset -> audio offset within the chapter (for tap-to-seek).
export function timeAtChar(text: string, marks: ChapterMarks, char: number, chapterDur: number): number {
  if (marks && marks.length) {
    const i = bisectMarks(marks, char, 0);
    const [cEnd, tEnd] = marks[i];
    const cPrev = i > 0 ? marks[i - 1][0] : 0;
    const tPrev = i > 0 ? marks[i - 1][1] : 0;
    const f = cEnd > cPrev ? clamp01((char - cPrev) / (cEnd - cPrev)) : 1;
    return tPrev + f * (tEnd - tPrev);
  }
  return text.length > 0 ? (char / text.length) * chapterDur : 0;
}

// Page index containing a chapter-local char position.
export function pageForPosition(pages: Page[], chapter: number, char: number): number {
  for (let i = 0; i < pages.length; i++) {
    const p = pages[i];
    if (p.chapter === chapter && char >= p.charStart && char < p.charEnd) return i;
    if (p.chapter > chapter) return Math.max(0, i - 1);
  }
  return pages.length ? pages.length - 1 : 0;
}

// Estimate how many characters fit in a w×h box of reader text.
// 17px Newsreader averages ~8.1px/char; line-height is 1.75. The 0.74
// factor deliberately under-fills: sentences are placed whole, paragraph
// gaps and ragged last lines eat space, and a clipped line at the page
// bottom is worse than a slightly airy page.
export function charsPerPageFor(width: number, height: number): number {
  const cpl = Math.max(20, width / 8.1);
  const lines = Math.max(6, height / (17 * 1.75));
  return Math.round(cpl * lines * 0.74);
}
