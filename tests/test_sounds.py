import io
import sys
import wave

import pytest

from chesspuz import sounds


@pytest.mark.parametrize("name", sounds.NAMES)
def test_every_clip_is_a_short_mono_wav(name: str) -> None:
    data = sounds.clip(name)
    assert sounds.clip(name) is data  # cached: the bytes stay alive for async playback
    with wave.open(io.BytesIO(data), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == sounds.RATE
        seconds = handle.getnframes() / handle.getframerate()
    assert 0.02 <= seconds <= 0.5
    peak = max(
        abs(int.from_bytes(data[i : i + 2], "little", signed=True))
        for i in range(44, len(data) - 1, 2)
    )
    assert peak > 1000  # audible, not silence


def test_player_uses_its_backend_and_respects_enabled() -> None:
    played: list[tuple[str, int]] = []
    player = sounds.SoundPlayer(backend=lambda name, data: played.append((name, len(data))))
    player.play("move")
    assert played == [("move", len(sounds.clip("move")))]
    player.enabled = False
    player.play("capture")
    assert len(played) == 1


def test_player_swallows_backend_errors_but_warns_once(capsys) -> None:
    def broken(_name: str, _data: bytes) -> None:
        raise OSError("no audio device")

    player = sounds.SoundPlayer(backend=broken)
    player.play("wrong")  # no exception
    player.play("no-such-sound")  # KeyError swallowed too
    assert capsys.readouterr().err.count("sound playback failed") == 1


def test_default_backend_really_plays_without_raising(tmp_path) -> None:
    backend = sounds.default_backend(tmp_path)
    backend("click", sounds.clip("click"))  # must not raise (winsound on Windows, no-op elsewhere)
    backend("click", sounds.clip("click"))
    if sys.platform == "win32":
        assert (tmp_path / "click.wav").read_bytes() == sounds.clip("click")
    assert isinstance(sounds.player, sounds.SoundPlayer)
