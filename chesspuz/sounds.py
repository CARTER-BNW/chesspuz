"""Synthesised sound effects and a tiny player. Headless; no Qt, no audio files.

Clips are generated on first use as mono 16-bit WAV bytes and played through ``winsound`` on
Windows (silently ignored elsewhere). The UI shares one :data:`player`; tests swap in a backend
that just records what was played.
"""

from __future__ import annotations

import io
import math
import random
import wave
from collections.abc import Callable

RATE = 22050
NAMES = ("click", "move", "capture", "correct", "wrong")

Backend = Callable[[bytes], None]


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


def _synth(name: str) -> bytes:
    if name == "click":
        return _wav(_tone(1800, 30, volume=0.25, decay=40, noise=0.3))
    if name == "move":
        return _wav(_tone(170, 90, freq_end=120, volume=0.7, decay=18, noise=0.35))
    if name == "capture":
        return _wav(_tone(120, 150, freq_end=70, volume=0.9, decay=12, noise=0.6))
    if name == "correct":
        first = _tone(660, 110, volume=0.35, decay=9, harmonics=(1.0, 0.2))
        second = _tone(880, 200, volume=0.35, decay=6, harmonics=(1.0, 0.2))
        return _wav(first + second)
    if name == "wrong":
        return _wav(_tone(220, 280, freq_end=140, volume=0.45, decay=5, harmonics=(1.0, 0.5, 0.3)))
    raise KeyError(name)


_CLIPS: dict[str, bytes] = {}


def clip(name: str) -> bytes:
    """WAV bytes for a named effect (cached; the bytes must outlive an async playback)."""
    if name not in _CLIPS:
        _CLIPS[name] = _synth(name)
    return _CLIPS[name]


def _silent(_data: bytes) -> None:
    return None


def default_backend() -> Backend:
    try:
        import winsound
    except ImportError:
        return _silent
    flags = winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT

    def play(data: bytes) -> None:
        winsound.PlaySound(data, flags)

    return play


class SoundPlayer:
    def __init__(self, backend: Backend | None = None, enabled: bool = True) -> None:
        self.backend = backend or default_backend()
        self.enabled = enabled

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        try:
            self.backend(clip(name))
        except Exception:  # noqa: BLE001 (a sound must never break the game)
            pass


#: Shared player used by the UI; the settings page toggles ``enabled``.
player = SoundPlayer()
