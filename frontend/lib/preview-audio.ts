// One shared controller for the home-page listening booth: a voice sample
// and an ambiance loop that play TOGETHER, voice on top, ambiance at its
// chosen volume underneath — the same mix mux_m4b renders, so what you
// hear while configuring is what the audiobook will sound like.

type VoiceEndCallback = () => void;

class PreviewAudio {
  private voiceEl: HTMLAudioElement | null = null;
  private ambEl: HTMLAudioElement | null = null;
  private onVoiceEnd: VoiceEndCallback | null = null;
  currentVoice: string | null = null;

  playVoice(id: string, speed: number, onEnd: VoiceEndCallback) {
    this.stopVoice();
    const el = new Audio(`/voice-sample/${id}`);
    // preservesPitch keeps the live speed preview honest: Kokoro renders
    // at the chosen tempo without chipmunking, and so does this.
    el.preservesPitch = true;
    el.playbackRate = speed;
    el.onended = () => {
      this.currentVoice = null;
      onEnd();
    };
    el.play().catch(() => {
      this.currentVoice = null;
      onEnd();
    });
    this.voiceEl = el;
    this.currentVoice = id;
    this.onVoiceEnd = onEnd;
  }

  stopVoice() {
    if (this.voiceEl) {
      this.voiceEl.pause();
      this.voiceEl.onended = null;
      this.voiceEl = null;
    }
    if (this.onVoiceEnd) {
      const cb = this.onVoiceEnd;
      this.onVoiceEnd = null;
      cb();
    }
    this.currentVoice = null;
  }

  setSpeed(speed: number) {
    if (this.voiceEl) this.voiceEl.playbackRate = speed;
  }

  playAmbiance(id: string, volume: number) {
    this.stopAmbiance();
    if (!id) return;
    const el = new Audio(`/ambiance/${id}`);
    el.loop = true;
    el.volume = Math.max(0, Math.min(1, volume / 100));
    el.play().catch(() => {});
    this.ambEl = el;
  }

  setAmbianceVolume(volume: number) {
    if (this.ambEl) this.ambEl.volume = Math.max(0, Math.min(1, volume / 100));
  }

  stopAmbiance() {
    if (this.ambEl) {
      this.ambEl.pause();
      this.ambEl = null;
    }
  }

  stopAll() {
    this.stopVoice();
    this.stopAmbiance();
  }
}

// Module singleton — survives component re-renders, dies with the page.
export const previewAudio = new PreviewAudio();
