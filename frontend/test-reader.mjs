// Quick sanity harness for the reader engine (run: node test-reader.mjs).
// Not a test framework on purpose — this is a kitchen-table check.
import { splitParas, buildPages, pageForPosition } from "./lib/reader.ts";

const sample =
  'The incredible rate at which the little girl escalated the conversation knocked Subaru into shell-shock. ' +
  'Without this girl, would he really get so lonely that he could not go on living anymore? How exaggerated could it get? ' +
  '???: “Hmph, even if you tell me you’ve forgotten, I’ll make you remember, I suppose—— Betty’s Contractor is just an annoying, noisy man. In fact.” ' +
  'Subaru: “There was a lot in there I didn’t understand... but was it all that supposed to be about Setting “Contractor”, or whatever?” ' +
  'He scratched his head. The downcast expression on the little girl’s face seemed to have lifted. ' +
  'Emilia: “Umm, Subaru... everything alright? Sorry, but we should get going soon.” That voice pulled him back.';

const paras = splitParas(sample);
console.log("paras:", paras.length);
for (const p of paras) {
  const first = p.sentences[0];
  console.log(
    (p.speakerLen ? `[DLG ${first.text.slice(0, p.speakerLen)}]` : "[NAR]").padEnd(16),
    `${p.sentences.length} sent`,
    JSON.stringify(first.text.slice(0, 58)) + "…"
  );
}

// Offsets must reconstruct the original text exactly.
let ok = true;
for (const p of paras) {
  for (const s of p.sentences) {
    if (sample.slice(s.start, s.start + s.text.length) !== s.text) {
      ok = false;
      console.log("OFFSET MISMATCH at", s.start, JSON.stringify(s.text.slice(0, 40)));
    }
  }
}
console.log("offsets exact:", ok);

// Image pages slot at their anchors and never capture the live position.
const chapters = [{ title: "Ch", text: sample, images: [{ char: 0, file: "a.jpg" }, { char: 300, file: "b.jpg" }] }];
const pages = buildPages(chapters, 280);
console.log("pages:", pages.map((p) => p.kind === "image" ? `img(${p.file})` : `text[${p.charStart}-${p.charEnd}]`).join(" "));
console.log("pos 305 -> page", pageForPosition(pages, 0, 305), "(must be a text page)");
console.log("page kind at that idx:", pages[pageForPosition(pages, 0, 305)].kind);
