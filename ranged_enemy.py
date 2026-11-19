"""사거리까지 접근하고 예고 없이 3초 간격으로 직선 탄환을 발사하는 적."""

from math import atan2, hypot

import game_framework
from enemy import MeleeEnemy
from projectile import Projectile


class RangedEnemy(MeleeEnemy):
    can_be_stunned = False
    sprite_actor = 'ranged'

    def __init__(self, identifier, data, x, y, player, add_projectile):
        super().__init__(identifier, data, x, y, player)
        self.add_projectile = add_projectile
        self.cooldown = 0.0
        self.shots = 0
        self.cast_age = float('inf')

    def stun(self, duration):
        # 원거리 적은 패링으로 스턴하지 않는다.
        pass

    def update(self):
        if self.hp <= 0 or self.player.combat.hp <= 0:
            return
        dt = game_framework.frame_time
        self.cooldown = max(0.0, self.cooldown - dt)
        self.cast_age += dt
        dx, dy = self.player.x - self.x, self.player.y - self.y
        distance = hypot(dx, dy)
        if distance > 0:
            self.angle = atan2(dy, dx)
        if distance > self.data['range_m'] + 1e-9:
            self.state = 'chase'
            step = min(distance - self.data['range_m'], self.data['speed_kmph'] / 3.6 * dt)
            self.walk_toward(dx / distance * step, dy / distance * step, dt)
            return
        self.state = 'shoot'
        self.moving, self.visual_time = False, 0.0
        if self.cooldown <= 1e-9:
            self.shots += 1
            self.add_projectile(Projectile(('bullet', self.identifier, self.shots), self.x, self.y,
                                           self.angle, self.data, self.player))
            self.cooldown = self.data['attack_interval_s']
            self.cast_age = 0.0

    def pose(self):
        if self.state == 'shoot' and self.cast_age < .5 and self.player.sprites:
            return 'cast', self.cast_age * self.player.sprites.fps
        return ('walk' if self.moving and self.state == 'chase' else 'idle'), None
