"""Voix off : edge-tts (voix neuronales gratuites) avec timings mot à mot.

Produit dans le dossier du sujet :
  audio.wav       — piste voix complète (mono 24 kHz, 16 bits)
  timeline.json   — segments + mots horodatés (pour sous-titres et animation)
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import wave
from pathlib import Path

import numpy as np

from .config import env

log = logging.getLogger("newsbot.tts")
SR = 24000
GAP = 0.16  # silence entre deux répliques (s)


def _voice_for(cfg, speaker: str) -> str:
    if speaker in ("a", "b"):
        return cfg["characters"][speaker]["voice"]
    return cfg["narrator_voice"]


async def _edge_segment(text: str, voice: str, rate: str, mp3_path: Path):
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"w": chunk["text"], "start": start,
                              "end": start + chunk["duration"] / 1e7})
    return words


def _mp3_to_pcm(mp3: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


def _estimate_words(text: str):
    """Timings estimés (mode hors ligne) : ~0,34 s par mot + pauses de ponctuation."""
    t, words = 0.0, []
    for w in text.split():
        d = 0.18 + 0.045 * len(w)
        words.append({"w": w, "start": t, "end": t + d})
        t += d + (0.22 if w[-1] in ".!?" else 0.08 if w[-1] in ",;:" else 0.03)
    return words, t


def synthesize(cfg, segments: list[dict], folder: Path) -> dict:
    backend = env("TTS_BACKEND", "edge")
    rate = cfg.get("tts_rate", "+0%")
    pieces, timeline, cursor = [], [], 0.25
    pieces.append(np.zeros(int(0.25 * SR), dtype=np.int16))
    for i, seg in enumerate(segments):
        text = seg["text"].strip()
        if backend == "edge":
            mp3 = folder / f"seg_{i:02d}.mp3"
            words = asyncio.run(_edge_segment(text, _voice_for(cfg, seg["speaker"]), rate, mp3))
            pcm = _mp3_to_pcm(mp3)
            mp3.unlink(missing_ok=True)
            dur = len(pcm) / SR
            if not words:
                words, _ = _estimate_words(text)
        else:  # silent : pour tester le rendu sans réseau
            words, dur = _estimate_words(text)
            pcm = np.zeros(int(dur * SR), dtype=np.int16)
        for w in words:
            w["start"] += cursor
            w["end"] += cursor
        timeline.append({**seg, "start": cursor, "end": cursor + dur, "words": words})
        pieces.append(pcm)
        gap = np.zeros(int(GAP * SR), dtype=np.int16)
        pieces.append(gap)
        cursor += dur + GAP
    pieces.append(np.zeros(int(0.4 * SR), dtype=np.int16))
    audio = np.concatenate(pieces)
    with wave.open(str(folder / "audio.wav"), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(audio.tobytes())
    result = {"duration": len(audio) / SR, "segments": timeline, "silent": backend != "edge"}
    (folder / "timeline.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    log.info("Voice: %.1f s (%s)", result["duration"], backend)
    return result
