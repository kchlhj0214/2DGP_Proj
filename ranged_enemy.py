"""사거리까지 접근하고 예고 없이 3초 간격으로 직선 탄환을 발사하는 적."""

from math import atan2, hypot

import pico2d

import game_framework
from enemy import MeleeEnemy
from projectile import Projectile


class RangedEnemy(MeleeEnemy):
    can_be_stunned = False

    def __init__(self, identifier, data, x, y, player, add_projectile):
        super().__init__(identifier, data, x, y, player)
        self.add_projectile = add_projectile
        self.cooldown = 0.0
        self.shots = 0

    def stun(self, duration):
        # 원거리 적은 패링으로 스턴하지 않는다.
        pass

    def update(self):
        if self.hp <= 0 or self.player.combat.hp <= 0:
            return
        dt = game_framework.frame_time
        self.cooldown = max(0.0, self.cooldown - dt)
        dx, dy = self.player.x - self.x, self.player.y - self.y
        distance = hypot(dx, dy)
        if distance > self.data['range_m'] + 1e-9:
            self.state = 'chase'
            step = min(distance - self.data['range_m'], self.data['speed_kmph'] / 3.6 * dt)
            self.x, self.y = self.player.constrain_position(
                self.x + dx / distance * step, self.y + dy / distance * step)
            return
        self.state = 'shoot'
        if self.cooldown <= 1e-9:
            self.shots += 1
            self.add_projectile(Projectile(('bullet', self.identifier, self.shots), self.x, self.y,
                                           atan2(dy, dx), self.data, self.player))
            self.cooldown = self.data['attack_interval_s']

    def draw(self):
        if self.hp > 0:
            super().draw()
            camera = self.player.camera
            x1, y1 = camera.to_screen(self.x - self.width / 2, self.y - self.height / 2)
            x2, y2 = camera.to_screen(self.x + self.width / 2, self.y + self.height / 2)
            pico2d.draw_rectangle(x1, y1, x2, y2, 114, 170, 245, filled=True)
            pico2d.draw_rectangle(x1, y1, x2, y2, 207, 230, 255)
