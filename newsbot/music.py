"""Original light news-bed, synthesised from scratch (no samples, no copyright issues).

100 BPM, 8-bar loop: soft pad, plucked arpeggio, sub bass, gentle kick and hi-hats.
Generated once into assets/music/news_bed.wav; ffmpeg loops it under the voice.
"""
from __future__ import annotations

import wave

import numpy as np

from .config import ASSETS

SR = 44100
BPM = 100
BEAT = 60 / BPM
# Am – F – C – G, two bars each (MIDI notes)
CHORDS = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _tone(freq, dur, harmonics=(1.0, 0.35, 0.15, 0.07), detune=0.0):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for k, amp in enumerate(harmonics, 1):
        out += amp * np.sin(2 * np.pi * freq * k * (1 + detune) * t)
    return out


def _env(n, attack=0.01, release=0.2, decay=None):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(attack, 1e-4))
    if decay:
        e *= np.exp(-t / decay)
    rel = int(release * SR)
    if rel and rel < n:
        e[-rel:] *= np.linspace(1, 0, rel)
    return e


def generate(path=None):
    path = path or ASSETS / "music" / "news_bed.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    bars = 8
    total = int(bars * 4 * BEAT * SR)
    L = np.zeros(total)
    R = np.zeros(total)
    rng = np.random.default_rng(60)

    def add(sig, start_s, pan=0.0, gain=1.0):
        a = int(start_s * SR)
        b = min(total, a + len(sig))
        L[a:b] += sig[:b - a] * gain * (1 - pan) * 0.5 * 2
        R[a:b] += sig[:b - a] * gain * (1 + pan) * 0.5 * 2

    for bar in range(bars):
        chord = CHORDS[(bar // 2) % 4]
        t0 = bar * 4 * BEAT
        # pad: whole bar, two slightly detuned layers
        for note in chord:
            n = int(4 * BEAT * SR)
            for det, pan in ((-0.003, -0.5), (0.003, 0.5)):
                sig = _tone(_hz(note), 4 * BEAT, (1, .3, .1), det) * _env(n, .4, .5)
                add(sig, t0, pan, 0.045)
        # sub bass on beats 1 and 3
        for beat in (0, 2):
            sig = _tone(_hz(chord[0] - 24), BEAT * 1.6, (1, .2)) * _env(int(BEAT * 1.6 * SR), .01, .2, .5)
            add(sig, t0 + beat * BEAT, 0, 0.16)
        # plucked arpeggio, 8th notes
        arp = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12]
        for s in range(8):
            note = arp[s % 4] + (12 if (bar % 2 and s in (6, 7)) else 0)
            d = BEAT * 0.5
            sig = _tone(_hz(note), d * 1.8, (1, .5, .2, .1)) * _env(int(d * 1.8 * SR), .002, .05, .18)
            add(sig, t0 + s * d, 0.35 if s % 2 else -0.35, 0.05)
        # kick on 1 and 3, hats on 8ths
        for beat in range(4):
            if beat in (0, 2):
                n = int(0.25 * SR)
                t = np.arange(n) / SR
                f = 110 * np.exp(-t * 25) + 45
                sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)
                add(sig, t0 + beat * BEAT, 0, 0.22)
            for half in (0, 1):
                n = int(0.05 * SR)
                noise = rng.standard_normal(n)
                hp = np.diff(noise, prepend=0)  # crude high-pass
                sig = hp * np.exp(-np.arange(n) / SR * 90)
                add(sig, t0 + (beat + half * 0.5) * BEAT, 0.2, 0.03 if half else 0.045)

    mix = np.stack([L, R], axis=1)
    # short crossfade at the loop point so it loops seamlessly
    fade = int(0.01 * SR)
    mix[:fade] *= np.linspace(0, 1, fade)[:, None]
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix /= np.max(np.abs(mix)) + 1e-9
    mix *= 0.6
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def ensure():
    path = ASSETS / "music" / "news_bed.wav"
    if not path.exists():
        generate(path)
    return path


if __name__ == "__main__":
    print(generate())


def generate_sting(path=None):
    """Original logo sting for the welcome intro: soft riser whoosh → one low hit (≈0.7 s)."""
    path = path or ASSETS / "music" / "breaking_sting.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    total = int(0.8 * SR)
    L = np.zeros(total)
    R = np.zeros(total)
    rng = np.random.default_rng(7)

    def add(sig, at, gain=1.0, pan=0.0):
        a = int(at * SR)
        b = min(total, a + len(sig))
        L[a:b] += sig[:b - a] * gain * (1 - pan)
        R[a:b] += sig[:b - a] * gain * (1 + pan)

    # 1) reverse-whoosh riser (0.00 → 0.18): filtered noise swelling up
    n = int(0.2 * SR)
    noise = rng.standard_normal(n)
    smooth = np.convolve(noise, np.ones(6) / 6, mode="same")
    add(smooth * np.linspace(0, 1, n) ** 2, 0.0, 0.25)
    # 2) one soft, low "hit" as the logo lands (no sustained chord)
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 80 * np.exp(-t * 6) + 40
    thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    add(thump, 0.18, 0.8)
    mix = np.stack([L, R], axis=1)
    fade = int(0.2 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix /= np.max(np.abs(mix)) + 1e-9
    mix *= 0.5
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def ensure_sting():
    path = ASSETS / "music" / "intro_sting_v2.wav"
    if not path.exists():
        generate_sting(path)
    return path
