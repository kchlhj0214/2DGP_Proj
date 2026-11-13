"""Python + pico2d 크기 확인용 첫 실행점."""

from ctypes import byref

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

    width, height = desktop_size()
    pico2d.open_canvas(width, height, sync=True, full=True)
    try:
        game_framework.run(play_mode)
    finally:
        pico2d.close_canvas()


if __name__ == '__main__':
    main()
