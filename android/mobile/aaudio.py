"""Sound on the phone through Android's AAudio C API (``libaaudio.so``, Android 8.1+) via ctypes.

The desktop plays the synthesised clips with winsound; PySide6's Android build has no Java
bridge and QtMultimedia would add 30 MB of ffmpeg, so the phone writes the PCM samples straight
to an AAudio output stream. Clips are short, so a single stream and a worker thread that plays
them one after another is enough. The conversion helpers are pure Python and tested on the PC;
the stream code only runs on the device.
"""

from __future__ import annotations

import array
import ctypes
import io
import queue
import sys
import threading
import wave
from collections.abc import Callable

AAUDIO_DIRECTION_OUTPUT = 0
AAUDIO_FORMAT_PCM_I16 = 1
AAUDIO_PERFORMANCE_MODE_LOW_LATENCY = 12
AAUDIO_USAGE_GAME = 14
AAUDIO_CONTENT_TYPE_SONIFICATION = 4
TIMEOUT_NS = 1_000_000_000


def decode_wav(data: bytes) -> tuple[array.array, int, int]:
    """16-bit PCM samples (interleaved), channel count and sample rate of a WAV file."""
    with wave.open(io.BytesIO(data), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("only 16-bit WAV clips are supported")
        channels, rate = handle.getnchannels(), handle.getframerate()
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples, channels, rate


def convert(
    samples: array.array, channels: int, rate: int, *, to_channels: int, to_rate: int
) -> array.array:
    """Resample (linear interpolation) and re-channel mono/stereo 16-bit PCM."""
    if channels not in (1, 2) or to_channels not in (1, 2):
        raise ValueError("mono or stereo only")
    if channels == 2:  # fold to mono first
        samples = array.array(
            "h", [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)]
        )
    if to_rate != rate and len(samples) > 1:
        count = max(1, round(len(samples) * to_rate / rate))
        step = (len(samples) - 1) / max(1, count - 1)
        out = array.array("h")
        for index in range(count):
            pos = index * step
            base = int(pos)
            nxt = min(base + 1, len(samples) - 1)
            frac = pos - base
            out.append(int(samples[base] * (1 - frac) + samples[nxt] * frac))
        samples = out
    if to_channels == 2:
        samples = array.array("h", [s for s in samples for _ in (0, 1)])
    return samples


class AAudioPlayer:
    """One output stream, clips played sequentially on a worker thread."""

    def __init__(self, lib: ctypes.CDLL | None = None) -> None:
        self.lib = lib or ctypes.CDLL("libaaudio.so")
        self._declare()
        self.stream: ctypes.c_void_p | None = None
        self.rate = 0
        self.channels = 0
        self.queue: queue.Queue[bytes | None] = queue.Queue()
        self.failed: str | None = None
        self._thread = threading.Thread(target=self._run, name="chesspuz-aaudio", daemon=True)
        self._thread.start()

    def _declare(self) -> None:
        lib = self.lib
        p = ctypes.c_void_p
        lib.AAudio_createStreamBuilder.argtypes = [ctypes.POINTER(p)]
        lib.AAudio_createStreamBuilder.restype = ctypes.c_int32
        for name in (
            "setDirection",
            "setFormat",
            "setChannelCount",
            "setSampleRate",
            "setPerformanceMode",
            "setUsage",
            "setContentType",
        ):
            fn = getattr(lib, f"AAudioStreamBuilder_{name}")
            fn.argtypes = [p, ctypes.c_int32]
            fn.restype = None
        lib.AAudioStreamBuilder_openStream.argtypes = [p, ctypes.POINTER(p)]
        lib.AAudioStreamBuilder_openStream.restype = ctypes.c_int32
        lib.AAudioStreamBuilder_delete.argtypes = [p]
        lib.AAudioStreamBuilder_delete.restype = ctypes.c_int32
        for name in ("requestStart", "requestStop", "close", "getSampleRate", "getChannelCount"):
            fn = getattr(lib, f"AAudioStream_{name}")
            fn.argtypes = [p]
            fn.restype = ctypes.c_int32
        lib.AAudioStream_write.argtypes = [p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int64]
        lib.AAudioStream_write.restype = ctypes.c_int32

    def _open(self) -> None:
        lib = self.lib
        builder = ctypes.c_void_p()
        result = lib.AAudio_createStreamBuilder(ctypes.byref(builder))
        if result < 0:
            raise OSError(f"AAudio_createStreamBuilder failed: {result}")
        try:
            lib.AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_OUTPUT)
            lib.AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_I16)
            lib.AAudioStreamBuilder_setChannelCount(builder, 1)
            lib.AAudioStreamBuilder_setSampleRate(builder, 22050)
            lib.AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY)
            lib.AAudioStreamBuilder_setUsage(builder, AAUDIO_USAGE_GAME)
            lib.AAudioStreamBuilder_setContentType(builder, AAUDIO_CONTENT_TYPE_SONIFICATION)
            stream = ctypes.c_void_p()
            result = lib.AAudioStreamBuilder_openStream(builder, ctypes.byref(stream))
            if result < 0:
                raise OSError(f"AAudioStreamBuilder_openStream failed: {result}")
        finally:
            lib.AAudioStreamBuilder_delete(builder)
        self.stream = stream
        self.rate = lib.AAudioStream_getSampleRate(stream)
        self.channels = lib.AAudioStream_getChannelCount(stream)
        result = lib.AAudioStream_requestStart(stream)
        if result < 0:
            raise OSError(f"AAudioStream_requestStart failed: {result}")

    def _close(self) -> None:
        if self.stream is not None:
            self.lib.AAudioStream_requestStop(self.stream)
            self.lib.AAudioStream_close(self.stream)
            self.stream = None

    def _write(self, data: bytes) -> None:
        samples, channels, rate = decode_wav(data)
        if self.stream is None:
            self._open()
        pcm = convert(samples, channels, rate, to_channels=self.channels, to_rate=self.rate)
        raw = pcm.tobytes()
        frames = len(pcm) // max(1, self.channels)
        buffer = ctypes.create_string_buffer(raw, len(raw))
        offset = 0
        while offset < frames:
            chunk = ctypes.addressof(buffer) + offset * self.channels * 2
            written = self.lib.AAudioStream_write(
                self.stream, ctypes.c_void_p(chunk), frames - offset, TIMEOUT_NS
            )
            if written < 0:
                self._close()
                raise OSError(f"AAudioStream_write failed: {written}")
            if written == 0:
                break
            offset += written

    def _run(self) -> None:
        while True:
            data = self.queue.get()
            if data is None:
                self._close()
                return
            try:
                self._write(data)
            except Exception as exc:  # noqa: BLE001 (sound must never break the game)
                if self.failed is None:
                    self.failed = repr(exc)
                    print(f"chesspuz: phone sound stopped: {self.failed}", file=sys.stderr)
                self._close()

    def play(self, _name: str, data: bytes) -> None:
        if self.failed is None:
            self.queue.put(data)

    def stop(self) -> None:
        self.queue.put(None)


def backend() -> Callable[[str, bytes], None]:
    """A ``sounds.Backend`` playing through AAudio (raises if libaaudio is unavailable)."""
    return AAudioPlayer().play
