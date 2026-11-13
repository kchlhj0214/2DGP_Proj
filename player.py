"""LEC11의 객체 구조와 LEC16의 시간 기반 이동을 적용한 플레이어."""

from math import hypot

import pico2d

import game_framework


class Player:
    def __init__(self, data, viewport, arena, camera):
        self.x = self.y = 0.0  # m
        self.height = viewport['height_m'] * data['height_ratio']
        self.width = self.height * data['width_height_ratio']
        self.boundary_height = self.height * data['boundary_height_ratio']
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

    def get_boundary_bb(self):
        """경기장 경계용 발밑 영역. 전체 히트박스의 하단 절반."""
        left, bottom, right, _ = self.get_bb()
        return left, bottom, right, bottom + self.boundary_height

    def constrain_position(self, x, y):
        """발밑 직사각형을 제한한 뒤 플레이어 중심 좌표로 복원한다."""
        offset_y = (self.height - self.boundary_height) / 2
        ground_x, ground_y = self.arena.constrain_box(
            x, y - offset_y, self.width, self.boundary_height)
        return ground_x, ground_y + offset_y

    def update(self):
        dx = int(pico2d.SDLK_d in self.pressed_keys) - int(pico2d.SDLK_a in self.pressed_keys)
        dy = int(pico2d.SDLK_w in self.pressed_keys) - int(pico2d.SDLK_s in self.pressed_keys)
        length = hypot(dx, dy)
        if length:
            distance = self.speed_mps * game_framework.frame_time
            self.x, self.y = self.constrain_position(
                self.x + dx / length * distance,
                self.y + dy / length * distance)

    def draw(self):
        left, bottom, right, top = self.get_bb()
        x1, y1 = self.camera.to_screen(left, bottom)
        x2, y2 = self.camera.to_screen(right, top)
        # 보이는 직사각형과 충돌 히트박스가 정확히 같다.
        pico2d.draw_rectangle(x1, y1, x2, y2, 64, 208, 192, filled=True)
        pico2d.draw_rectangle(x1, y1, x2, y2, 206, 255, 239)
        # 경계 판정에 쓰는 하단 영역을 가로선으로 구분한다.
        _, _, _, ground_top = self.get_boundary_bb()
        _, ground_y = self.camera.to_screen(self.x, ground_top)
        pico2d.draw_line(x1, ground_y, x2, ground_y, 206, 255, 239)
