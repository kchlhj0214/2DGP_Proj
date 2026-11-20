"""적의 직선 탄환: 원형 판정, 방어·패링·광선·경계에서 제거."""

from math import cos, hypot, pi, sin

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
        if self.active and self.player.sprites:
            self.player.sprites.draw_projectile(self, self.player.camera)
