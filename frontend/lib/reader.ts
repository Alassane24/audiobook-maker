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
//
// Layout: the web novel writes dialogue as `Name: “…”`, so paragraphs
// break at speaker labels — each speech starts its own line, narration
// groups into short paragraphs. Illustration scans from the source epub
// ride along as full art pages anchored at their position in the text.

export interface ChapterImage {
  char: number; // anchor offset in the chapter text
  file: string;
}

export interface ReaderChapter {
  title: string;
  text: string;
  images?: ChapterImage[];
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

export interface Para {
  sentences: Sentence[];
  speakerLen?: number; // chars of the `Name:` label opening the paragraph
}

export type Page =
  | { kind: "text"; chapter: number; charStart: number; charEnd: number; paras: Para[] }
  | { kind: "image"; chapter: number; charStart: number; charEnd: number; file: string };

export function splitSentences(text: string, offset = 0): Sentence[] {
  const out: Sentence[] = [];
  const re = /[^.!?…]+[.!?…]+[”’"')\]]*\s*|[^.!?…]+\s*$/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m[0].trim()) out.push({ text: m[0], start: offset + m.index });
    if (m.index === re.lastIndex) re.lastIndex++; // safety against zero-width stalls
  }
  return out;
}

// `Subaru: “…”` / `???: “…”` — a speaker label followed by an opening
// quote or bracket. Group 1 = leading boundary, group 2 = the label.
const SPEAKER_RE = /(^|\s)((?:[A-Z][\w'’.-]{0,24}|\?{3}):)(?=\s*[“"'\[])/g;

const opensIn = (s: string) => (s.match(/[“\[]/g) || []).length;
const closesIn = (s: string) => (s.match(/[”\]]/g) || []).length;

const NARRATION_GROUP = 4; // sentences per faux narration paragraph

// Split a chapter into paragraphs: dialogue speeches stand alone (label
// kept with the speech), narration groups into short paragraphs.
export function splitParas(text: string): Para[] {
  const cuts: { start: number; labelLen: number }[] = [];
  let m: RegExpExecArray | null;
  SPEAKER_RE.lastIndex = 0;
  while ((m = SPEAKER_RE.exec(text)) !== null) {
    cuts.push({ start: m.index + m[1].length, labelLen: m[2].length });
  }

  const paras: Para[] = [];
  const groupNarration = (sentences: Sentence[]) => {
    for (let i = 0; i < sentences.length; i += NARRATION_GROUP) {
      paras.push({ sentences: sentences.slice(i, i + NARRATION_GROUP) });
    }
  };

  let segStart = 0;
  for (let c = 0; c <= cuts.length; c++) {
    const segEnd = c < cuts.length ? cuts[c].start : text.length;
    if (segEnd > segStart) {
      const label = c > 0 ? cuts[c - 1] : null;
      let sentences: Sentence[];
      if (!label) {
        sentences = splitSentences(text.slice(segStart, segEnd), segStart);
      } else {
        // Split AFTER the label and glue it onto the first sentence —
        // labels like `???:` contain sentence terminators and would
        // otherwise be eaten by the splitter.
        const bodyStart = segStart + label.labelLen;
        sentences = splitSentences(text.slice(bodyStart, segEnd), bodyStart);
        if (sentences.length) {
          const f = sentences[0];
          sentences[0] = { text: text.slice(segStart, f.start) + f.text, start: segStart };
        } else {
          sentences = [{ text: text.slice(segStart, segEnd), start: segStart }];
        }
      }
      if (!label) {
        groupNarration(sentences);
      } else {
        // The segment runs from this label to the next one; the speech is
        // its leading part. Track curly-quote/bracket depth to find where
        // the quote closes, then group the trailing narration normally.
        const speech: Sentence[] = [];
        let depth = 0, opened = false, k = 0;
        for (; k < sentences.length; k++) {
          const s = sentences[k];
          speech.push(s);
          depth += opensIn(s.text) - closesIn(s.text);
          if (opensIn(s.text) > 0) opened = true;
          if (opened && depth <= 0) { k++; break; }
          if (!opened && k === 0) { k++; break; } // no quote chars at all: label line only
        }
        paras.push({ sentences: speech, speakerLen: label.labelLen });
        groupNarration(sentences.slice(k));
      }
    }
    segStart = segEnd;
  }
  return paras;
}

// Group sentences into pages of ~charsPerPage, breaking only between
// sentences; whole paragraphs stay together when they fit. Illustration
// pages are inserted at their character anchors.
export function buildPages(chapters: ReaderChapter[], charsPerPage: number): Page[] {
  const pages: Page[] = [];
  const budget = Math.max(280, charsPerPage);

  chapters.forEach((ch, ci) => {
    const imgs = (ch.images ?? []).slice().sort((a, b) => a.char - b.char);
    let ii = 0;

    let cur: Para[] = [];
    let curChars = 0;
    let pageStart = 0;
    let pageEnd = 0;

    const flush = () => {
      if (!cur.length) return;
      pages.push({ kind: "text", chapter: ci, charStart: pageStart, charEnd: pageEnd, paras: cur });
      cur = [];
      curChars = 0;
    };

    const pushPara = (para: Para) => {
      const len = para.sentences.reduce((n, s) => n + s.text.length, 0);
      if (curChars > 0 && curChars + len > budget) flush();
      if (len > budget && para.sentences.length > 1) {
        // A paragraph bigger than a page splits at sentence boundaries;
        // only the first piece keeps the speaker label styling.
        let piece: Sentence[] = [];
        let pieceLen = 0;
        let first = true;
        for (const s of para.sentences) {
          if (pieceLen > 0 && pieceLen + s.text.length > budget) {
            pushPara({ sentences: piece, speakerLen: first ? para.speakerLen : undefined });
            first = false;
            piece = [];
            pieceLen = 0;
          }
          piece.push(s);
          pieceLen += s.text.length;
        }
        if (piece.length) pushPara({ sentences: piece, speakerLen: first ? para.speakerLen : undefined });
        return;
      }
      if (cur.length === 0) pageStart = para.sentences[0].start;
      cur.push(para);
      curChars += len;
      const last = para.sentences[para.sentences.length - 1];
      pageEnd = last.start + last.text.length;
    };

    for (const para of splitParas(ch.text)) {
      const paraStart = para.sentences[0].start;
      while (ii < imgs.length && imgs[ii].char <= paraStart) {
        flush();
        pages.push({ kind: "image", chapter: ci, charStart: imgs[ii].char, charEnd: imgs[ii].char, file: imgs[ii].file });
        ii++;
      }
      pushPara(para);
    }
    flush();
    while (ii < imgs.length) {
      pages.push({ kind: "image", chapter: ci, charStart: imgs[ii].char, charEnd: imgs[ii].char, file: imgs[ii].file });
      ii++;
    }
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

// Page index containing a chapter-local char position. Image pages are
// zero-width, so they never capture the live position.
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
