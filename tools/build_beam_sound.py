"""Shape the selected large laser into a decaying, repeatable beam pulse."""

import ctypes
import json
import math
import os
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RATE = 44100


def source_samples():
    # Decode in a silent audio device, using the same mixer as the game.
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pico2d.pico2d as mixer

    path = ROOT / 'art/source/laserLarge_000.ogg'
    if mixer.SDL_Init(mixer.SDL_INIT_AUDIO) != 0:
        raise RuntimeError('오디오 작업 장치를 열 수 없습니다.')
    try:
        if mixer.Mix_OpenAudio(RATE, mixer.MIX_DEFAULT_FORMAT, 1, 1024) != 0:
            raise RuntimeError('효과음 디코더를 열 수 없습니다.')
        try:
            chunk = mixer.Mix_LoadWAV(str(path).encode('utf-8'))
            if not chunk:
                    raise ValueError(f'효과음 원본을 읽을 수 없습니다: {path}')
            try:
                raw = ctypes.string_at(chunk.contents.abuf, chunk.contents.alen)
                return struct.unpack(f'<{len(raw) // 2}h', raw)
            finally:
                mixer.Mix_FreeChunk(chunk)
        finally:
            mixer.Mix_CloseAudio()
    finally:
        mixer.SDL_QuitSubSystem(mixer.SDL_INIT_AUDIO)


def build():
    original = source_samples()
    combat = json.loads((ROOT / 'data/combat.json').read_text(encoding='utf-8'))
    interval = next(row for row in combat['systems'] if row['id'] == 'main')['beam_tick_s']
    duration = interval - .025
    pcm = []
    for frame in range(round(RATE * duration)):
        time = frame / RATE
        # Keep the start recognizable, then lengthen the falling portion.
        source_time = .003 + time - max(0, time - .07) * .19
        offset = source_time * RATE
        base = int(offset)
        if base + 1 >= len(original):
            break
        fraction = offset - base
        sample = original[base] * (1 - fraction) + original[base + 1] * fraction
        envelope = math.exp(-time * 5.7) * min(1, time / .005, (duration - time) / .075)
        pcm.append(round(sample * envelope))
    peak = max(abs(sample) for sample in pcm)
    pcm = [round(sample * 27000 / peak) for sample in pcm]
    with wave.open(str(ROOT / 'assets/audio/beam-pulse.wav'), 'wb') as output:
        output.setparams((1, 2, RATE, len(pcm), 'NONE', 'not compressed'))
        output.writeframes(struct.pack(f'<{len(pcm)}h', *pcm))


if __name__ == '__main__':
    build()
