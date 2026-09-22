"""Synthesised sound effects and a tiny player. Headless; no Qt, no audio files.

Clips are generated on first use as mono 16-bit WAV bytes. On Windows they are written once to
``<data dir>/sounds/<name>.wav`` and played with ``winsound`` asynchronously from that file
(Python's winsound cannot play asynchronously from memory); elsewhere playback is a no-op. The UI
shares one :data:`player`; tests swap in a backend that just records what was played.
"""

from __future__ import annotations

import io
import math
import random
import sys
import wave
from collections.abc import Callable
from pathlib import Path

RATE = 22050
NAMES = ("click", "move", "capture", "correct", "wrong")

#: ``backend(name, wav_bytes)`` plays one clip.
Backend = Callable[[str, bytes], None]


def _tone(
    freq_start: float,
    ms: int,
    *,
    freq_end: float | None = None,
    volume: float = 0.5,
    decay: float = 8.0,
    noise: float = 0.0,
    harmonics: tuple[float, ...] = (1.0,),
    seed: int = 1,
) -> list[float]:
    """A decaying tone (optionally sweeping and with odd harmonics) plus optional noise."""
    rng = random.Random(seed)
    count = int(RATE * ms / 1000)
    freq_end = freq_start if freq_end is None else freq_end
    samples: list[float] = []
    phase = 0.0
    for i in range(count):
        t = i / count
        freq = freq_start + (freq_end - freq_start) * t
        phase += 2 * math.pi * freq / RATE
        value = 0.0
        for k, weight in enumerate(harmonics):
            value += weight * math.sin(phase * (2 * k + 1))
        value += noise * (rng.random() * 2 - 1)
        envelope = math.exp(-decay * t)
        attack = min(1.0, i / (RATE * 0.002))  # 2 ms attack to avoid clicks
        samples.append(volume * value * envelope * attack)
    return samples


def _wav(samples: list[float]) -> bytes:
    data = bytearray()
    for sample in samples:
        clipped = max(-1.0, min(1.0, sample))
        data += int(clipped * 32767).to_bytes(2, "little", signed=True)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(bytes(data))
    return buffer.getvalue()


def _synth(name: str) -> list[float]:
    if name == "click":
        return _tone(1800, 30, volume=0.25, decay=40, noise=0.3)
    if name == "move":
        return _tone(170, 90, freq_end=120, volume=0.7, decay=18, noise=0.35)
    if name == "capture":
        return _tone(120, 150, freq_end=70, volume=0.9, decay=12, noise=0.6)
    if name == "correct":
        first = _tone(660, 110, volume=0.35, decay=9, harmonics=(1.0, 0.2))
        second = _tone(880, 200, volume=0.35, decay=6, harmonics=(1.0, 0.2))
        return first + second
    if name == "wrong":
        return _tone(220, 280, freq_end=140, volume=0.45, decay=5, harmonics=(1.0, 0.5, 0.3))
    raise KeyError(name)


_SAMPLES: dict[str, list[float]] = {}
_CLIPS: dict[tuple[str, int], bytes] = {}


def clip(name: str, volume: int = 100) -> bytes:
    """WAV bytes for a named effect at ``volume`` 0-100 (cached per name and volume)."""
    volume = max(0, min(100, int(volume)))
    key = (name, volume)
    if key not in _CLIPS:
        if name not in _SAMPLES:
            _SAMPLES[name] = _synth(name)
        scale = volume / 100
        _CLIPS[key] = _wav([sample * scale for sample in _SAMPLES[name]])
    return _CLIPS[key]


def _silent(_name: str, _data: bytes) -> None:
    return None


def default_backend(directory: Path | None = None) -> Backend:
    """winsound playing from WAV files under ``directory`` (default: the app data dir)."""
    try:
        import winsound
    except ImportError:
        return _silent
    flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    written: dict[str, tuple[Path, bytes]] = {}

    def play(name: str, data: bytes) -> None:
        entry = written.get(name)
        if entry is None or entry[1] != data:  # first play, or the clip changed (volume)
            folder = directory
            if folder is None:
                from chesspuz import paths

                folder = paths.data_dir() / "sounds"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{name}.wav"
            winsound.PlaySound(None, 0)  # stop any playback of the old file before rewriting
            path.write_bytes(data)
            entry = (path, data)
            written[name] = entry
        winsound.PlaySound(str(entry[0]), flags)

    return play


class SoundPlayer:
    def __init__(self, backend: Backend | None = None, enabled: bool = True) -> None:
        self.backend = backend or default_backend()
        self.enabled = enabled
        self.volumes: dict[str, int] = dict.fromkeys(NAMES, 100)
        self._warned = False

    def set_volume(self, name: str, volume: int) -> None:
        self.volumes[name] = max(0, min(100, int(volume)))

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        volume = self.volumes.get(name, 100)
        if volume <= 0:
            return
        try:
            self.backend(name, clip(name, volume))
        except Exception as exc:  # noqa: BLE001 (a sound must never break the game)
            if not self._warned:
                self._warned = True
                print(f"chesspuz: sound playback failed: {exc!r}", file=sys.stderr)


#: Shared player used by the UI; the settings page toggles ``enabled``.
player = SoundPlayer()
