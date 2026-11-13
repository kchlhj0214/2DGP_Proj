"""LEC11의 객체 구조와 LEC16의 시간 기반 이동을 적용한 플레이어."""

from math import hypot

import pico2d

import game_framework


class Player:
    def __init__(self, data, viewport, arena, camera):
        self.x = self.y = 0.0  # m
        self.height = viewport['height_m'] * data['height_ratio']
        self.width = self.height * data['width_height_ratio']
        self.speed_mps = data['speed_kmph'] * 1000.0 / 3600.0
        self.arena, self.camera = arena, camera
        self.pressed_keys = set()

    def handle_event(self, event):
        keys = (pico2d.SDLK_w, pico2d.SDLK_a, pico2d.SDLK_s, pico2d.SDLK_d)
        if event.type == pico2d.SDL_KEYDOWN and event.key in keys:
            self.pressed_keys.add(event.key)
        elif event.type == pico2d.SDL_KEYUP and event.key in keys:
            self.pressed_keys.discard(event.key)

    def pause(self):
        self.pressed_keys.clear()

    def get_bb(self):
        return (self.x - self.width / 2, self.y - self.height / 2,
                self.x + self.width / 2, self.y + self.height / 2)

    def update(self):
        dx = int(pico2d.SDLK_d in self.pressed_keys) - int(pico2d.SDLK_a in self.pressed_keys)
        dy = int(pico2d.SDLK_w in self.pressed_keys) - int(pico2d.SDLK_s in self.pressed_keys)
        length = hypot(dx, dy)
        if length:
            distance = self.speed_mps * game_framework.frame_time
            self.x, self.y = self.arena.constrain_box(
                self.x + dx / length * distance,
                self.y + dy / length * distance, self.width, self.height)

    def draw(self):
        left, bottom, right, top = self.get_bb()
        x1, y1 = self.camera.to_screen(left, bottom)
        x2, y2 = self.camera.to_screen(right, top)
        # 보이는 직사각형과 충돌 히트박스가 정확히 같다.
        pico2d.draw_rectangle(x1, y1, x2, y2, 64, 208, 192, filled=True)
        pico2d.draw_rectangle(x1, y1, x2, y2, 206, 255, 239)
