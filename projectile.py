"""적의 직선 탄환: 원형 판정, 방어·패링·광선·경계에서 제거."""

from math import cos, hypot, pi, sin

import pico2d

import game_framework
from geometry import box_points, circle_intersects_polygon


class Projectile:
    can_be_stunned = False

    def __init__(self, identifier, x, y, angle, data, player):
        self.identifier = identifier
        self.x, self.y, self.angle = x, y, angle
        self.incoming_angle = angle + pi
        self.data, self.player = data, player
        self.radius = data['projectile_radius_m']
        self.active = True
        self.result = None

    def update(self):
        if not self.active or self.player.combat.hp <= 0:
            return
        distance = self.data['projectile_speed_mps'] * game_framework.frame_time
        self.x += cos(self.angle) * distance
        self.y += sin(self.angle) * distance
        beam = self.player.combat.beam
        if beam and beam.active and circle_intersects_polygon(self.x, self.y, self.radius, beam.polygon()):
            self.active, self.result = False, 'beam'
        elif circle_intersects_polygon(self.x, self.y, self.radius, box_points(self.player.get_bb())):
            self.result = self.player.combat.receive(
                self.identifier, self, self.data['damage'], self.data['energy_gain'])
            self.active = False
        elif hypot(self.x, self.y) >= self.player.arena.radius:
            self.active, self.result = False, 'boundary'

    def draw(self):
        if self.active:
            camera = self.player.camera
            x, y = camera.to_screen(self.x, self.y)
            radius = max(2, round(self.radius * camera.pixels_per_meter))
            pico2d.draw_circle(x, y, radius, 83, 44, 125, filled=True)
            pico2d.draw_circle(x, y, max(1, radius - 1), 181, 111, 227, filled=True)
            pico2d.draw_circle(x - 1, y + 1, max(1, radius // 2), 244, 198, 255, filled=True)
