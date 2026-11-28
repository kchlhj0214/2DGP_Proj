"""LEC11의 객체 구조와 LEC16의 시간 기반 이동을 적용한 플레이어."""

from math import atan2, cos, hypot, pi, sin

import pico2d

import game_framework
from defense import PlayerCombat


class Player:
    def __init__(self, data, viewport, arena, camera):
        self.x = self.y = 0.0  # m
        self.height = viewport['height_m'] * data['height_ratio']
        self.width = self.height * data['width_height_ratio']
        self.boundary_height = self.height * data['boundary_height_ratio']
        self.speed_mps = data['speed_kmph'] * 1000.0 / 3600.0
        self.arena, self.camera = arena, camera
        self.pressed_keys = set()
        self.targets = []
        self.projectiles = []
        self.sprites = self.effects = None
        self.moving = False
        self.knockback = None
        self.visual_motion, self.visual_time = 'idle', 0.0
        self.visual_angle = -pi / 2
        self.combat = PlayerCombat(self)

    def handle_event(self, event):
        if event.type == pico2d.SDL_MOUSEMOTION:
            x, y = self.camera.to_world(event.x, self.camera.height_px - 1 - event.y)
            if (x, y) != (self.x, self.y):
                self.combat.aim = atan2(y - self.y, x - self.x)
        elif event.type == pico2d.SDL_MOUSEBUTTONDOWN:
            if event.button == pico2d.SDL_BUTTON_RIGHT:
                self.combat.right_down()
            elif event.button == pico2d.SDL_BUTTON_LEFT:
                self.combat.fire()
        elif event.type == pico2d.SDL_MOUSEBUTTONUP and event.button == pico2d.SDL_BUTTON_RIGHT:
            self.combat.right_up()
        keys = (pico2d.SDLK_w, pico2d.SDLK_a, pico2d.SDLK_s, pico2d.SDLK_d)
        if event.type == pico2d.SDL_KEYDOWN and event.key in keys:
            self.pressed_keys.add(event.key)
        elif event.type == pico2d.SDL_KEYUP and event.key in keys:
            self.pressed_keys.discard(event.key)

    def pause(self):
        self.pressed_keys.clear()
        self.combat.right_up()

    def get_bb(self):
        return (self.x - self.width / 2, self.y - self.height / 2,
                self.x + self.width / 2, self.y + self.height / 2)

    def get_boundary_bb(self):
        """경기장 경계용 발밑 영역. 전체 히트박스의 하단 절반."""
        left, bottom, right, _ = self.get_bb()
        return left, bottom, right, bottom + self.boundary_height

    def beam_pose(self):
        motion = 'guard_walk' if self.visual_motion == 'run' else 'guard'
        return motion, self.visual_time

    def constrain_position(self, x, y):
        """발밑 직사각형을 제한한 뒤 플레이어 중심 좌표로 복원한다."""
        offset_y = (self.height - self.boundary_height) / 2
        ground_x, ground_y = self.arena.constrain_box(
            x, y - offset_y, self.width, self.boundary_height)
        return ground_x, ground_y + offset_y

    def start_knockback(self, angle, distance, duration):
        target = self.constrain_position(self.x + cos(angle) * distance, self.y + sin(angle) * distance)
        self.knockback = (self.x, self.y, *target, duration, 0.0)

    def advance_knockback(self, dt):
        if self.knockback is None or self.combat.hp <= 0:
            return 0.0
        x, y, end_x, end_y, duration, age = self.knockback
        used = min(dt, duration - age)
        age += used
        progress = 1 - (1 - age / duration) ** 2
        self.x, self.y = x + (end_x - x) * progress, y + (end_y - y) * progress
        self.knockback = (x, y, end_x, end_y, duration, age) if age < duration else None
        return used

    def update(self):
        dt = game_framework.frame_time
        before = (self.x, self.y)
        sliding = self.advance_knockback(dt)
        moving_dt = max(0.0, dt - max(sliding, self.combat.position_lock_remaining()))
        self.combat.advance(dt)
        dx = int(pico2d.SDLK_d in self.pressed_keys) - int(pico2d.SDLK_a in self.pressed_keys)
        dy = int(pico2d.SDLK_w in self.pressed_keys) - int(pico2d.SDLK_s in self.pressed_keys)
        length = hypot(dx, dy)
        if length and moving_dt > 1e-9 and self.combat.state != 'dead':
            speed = (self.combat.settings['guard_kmph'] / 3.6
                     if self.combat.state == 'guard' else self.speed_mps)
            distance = speed * moving_dt
            self.x, self.y = self.constrain_position(
                self.x + dx / length * distance,
                self.y + dy / length * distance)
        self.moving = sliding == 0 and hypot(self.x - before[0], self.y - before[1]) > 1e-9
        state = self.combat.state
        if state == 'guard' or self.combat.position_lock_remaining() > 1e-9:
            self.visual_angle = self.combat.aim
        elif state == 'beam':
            self.visual_angle = self.combat.beam.angle
        elif length and state != 'dead':
            self.visual_angle = atan2(dy, dx)
        motion = ('guard_walk' if self.moving else 'guard') if state == 'guard' else ('run' if self.moving else 'idle')
        self.visual_time = self.visual_time + dt if self.visual_motion == motion else 0.0
        self.visual_motion = motion
        self.combat.update_beam(dt)

    def draw(self):
        self.combat.draw()
        if not self.sprites:
            return
        flash = self.effects and self.effects.player_flash_color()
        motion, angle, frame = self.visual_motion, self.visual_angle, None
        if self.combat.position_lock_remaining() > 1e-9:
            motion, angle, frame = 'parry', self.combat.aim, self.combat.parry_frame()
        elif self.combat.state == 'guard':
            motion = 'guard_walk_front' if self.combat.walking_guard() else 'guard'
            angle = self.combat.aim
        elif self.combat.state == 'beam':
            angle = self.combat.beam.angle
            motion, _ = self.beam_pose()
        self.sprites.draw('hero', motion, self, self.camera, angle, self.visual_time, frame, flash)
        if self.combat.beam:
            self.combat.beam.draw_emitter()
