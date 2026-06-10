// Kokoro voice catalog — mirrors VOICE_CARDS in web/app.py. Static on
// purpose: the voices ship with the model, and samples/voices/*.wav are
// pre-rendered preview clips served at /voice-sample/{id}.

export interface Voice {
  id: string;
  name: string;
  tag: string;
  desc: string;
}

export const VOICES: Voice[] = [
  { id: "af_heart",   name: "Heart",   tag: "American · Warm",   desc: "Natural and warm — the default" },
  { id: "af_bella",   name: "Bella",   tag: "American · Crisp",  desc: "Clear and articulate" },
  { id: "af_nicole",  name: "Nicole",  tag: "American · Soft",   desc: "Soft, breathy" },
  { id: "am_michael", name: "Michael", tag: "American · Male",   desc: "Neutral narrator" },
  { id: "am_fenrir",  name: "Fenrir",  tag: "American · Deep",   desc: "Deeper male voice" },
  { id: "bf_emma",    name: "Emma",    tag: "British · Female",  desc: "Classic audiobook" },
  { id: "bm_george",  name: "George",  tag: "British · Male",    desc: "British male" },
];

export const DEFAULT_VOICE = "af_heart";

export interface Ambiance {
  id: "" | "rain" | "fire";
  name: string;
}

export const AMBIANCES: Ambiance[] = [
  { id: "", name: "None" },
  { id: "rain", name: "Soft Rain" },
  { id: "fire", name: "Crackling Fireplace" },
];

export interface Quality {
  id: "compact" | "standard" | "high";
  name: string;
  hint: string;
}

export const QUALITIES: Quality[] = [
  { id: "compact", name: "Compact", hint: "smaller file" },
  { id: "standard", name: "Standard", hint: "recommended" },
  { id: "high", name: "High", hint: "best fidelity" },
];
