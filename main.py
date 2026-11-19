"""Shield Attack entry point."""

from ctypes import byref
from pathlib import Path

import pico2d

import game_framework
from tools.generate_data import generate


def desktop_size():
    # pico2d가 공개하는 SDL API로 현재 모니터 해상도를 읽는다.
    if pico2d.SDL_Init(pico2d.SDL_INIT_VIDEO) != 0:
        raise RuntimeError('화면 정보를 읽을 수 없습니다.')
    try:
        mode = pico2d.SDL_DisplayMode()
        if pico2d.SDL_GetCurrentDisplayMode(0, byref(mode)) != 0:
            raise RuntimeError('현재 모니터 해상도를 읽을 수 없습니다.')
        return mode.w, mode.h
    finally:
        pico2d.SDL_QuitSubSystem(pico2d.SDL_INIT_VIDEO)


def main():
    # 항상 시트 검증과 코드 생성을 먼저 마친다.
    generate()
    import play_mode

    from game_data import VIEWPORTS

    report = Path.cwd() / 'patch-test.txt'
    play_mode.test_path = report if report.is_file() else None

    viewport = VIEWPORTS['main']
    desktop_width, desktop_height = desktop_size()
    scale = min(1.0,
                desktop_width * viewport['desktop_fit_ratio'] / viewport['window_width_px'],
                desktop_height * viewport['desktop_fit_ratio'] / viewport['window_height_px'])
    width = int(viewport['window_width_px'] * scale)
    height = int(viewport['window_height_px'] * scale)
    pico2d.open_canvas(width, height, sync=True, full=False)
    try:
        game_framework.run(play_mode)
    finally:
        pico2d.close_canvas()


if __name__ == '__main__':
    main()
