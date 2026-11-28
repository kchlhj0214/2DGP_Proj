"""Session-wide volume shared by the lobby and the pause menu."""

import pico2d


volume = 100


def set_volume(percent):
    global volume
    volume = max(0, min(100, round(percent)))
    level = round(128 * volume / 100)
    pico2d.Mix_Volume(-1, level)
    pico2d.Mix_VolumeMusic(level)
