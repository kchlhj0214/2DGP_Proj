"""방향을 고정한 뒤 회전하는 칼 히트박스로 한 번 공격하는 근접 적."""

from math import atan2, hypot, radians

import pico2d

import game_framework
from game_data import CHARACTERS, VIEWPORTS
from geometry import box_points, draw_polygon, draw_sector, intersects, oriented_box


class MeleeEnemy:
    def __init__(self, identifier, data, x, y, player):
        self.identifier, self.data, self.player = identifier, data, player
        self.x, self.y = x, y
        character = CHARACTERS[data['character_id']]
        self.height = VIEWPORTS[character['viewport_id']]['height_m'] * character['height_ratio']
        self.width = self.height * character['width_height_ratio']
        self.hp = data['hp']
        self.state = 'chase'
        self.age = 0.0
        self.angle = 0.0
        self.attack_count = 0
        self.attack_id = None
        self.hit = False
        self.stun_duration = 0.0

    def get_bb(self):
        return (self.x - self.width / 2, self.y - self.height / 2,
                self.x + self.width / 2, self.y + self.height / 2)

    def stun(self, duration):
        if self.hp > 0:
            self.state, self.age = 'stunned', 0.0
            self.stun_duration = duration
            self.attack_id = None

    def take_damage(self, amount):
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.state = 'dead'
            self.attack_id = None

    def update(self):
        if self.hp <= 0 or self.player.combat.hp <= 0:
            return
        if self.state == 'stunned':
            self.age += game_framework.frame_time
            if self.age >= self.stun_duration:
                self.state, self.age = 'chase', 0.0
            return
        dx, dy = self.player.x - self.x, self.player.y - self.y
        distance = hypot(dx, dy)
        if distance > self.data['stop_m']:
            step = min(distance - self.data['stop_m'], self.data['speed_kmph'] / 3.6 * game_framework.frame_time)
            self.x, self.y = self.player.constrain_position(
                self.x + dx / distance * step, self.y + dy / distance * step)

    def draw(self):
        if self.hp <= 0:
            return
        camera = self.player.camera
        color = (224, 114, 99) if self.state != 'stunned' else (167, 137, 220)
        left, bottom, right, top = self.get_bb()
        x1, y1 = camera.to_screen(left, bottom)
        x2, y2 = camera.to_screen(right, top)
        pico2d.draw_rectangle(x1, y1, x2, y2, *color, filled=True)
        pico2d.draw_rectangle(x1, y1, x2, y2, 255, 212, 194)
        pico2d.draw_rectangle(x1, y2 + 4, x2, y2 + 7, 64, 40, 43, filled=True)
        pico2d.draw_rectangle(x1, y2 + 4, x1 + (x2 - x1) * self.hp / self.data['hp'],
                              y2 + 7, 237, 116, 113, filled=True)
