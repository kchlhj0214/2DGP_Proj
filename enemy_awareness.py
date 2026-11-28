"""적의 감지와 마지막 목격 지점 수색."""

from math import cos, hypot, sin, sqrt, tau
from random import random

from enemy_spacing import EPSILON


class EnemyAwareness:
    def __init__(self, detection_radius, search_radius):
        self.detection_radius = detection_radius
        self.search_radius = search_radius
        self.last_seen = None
        self.destination = None
        self.travel_budget = 0.0

    def observe(self, enemy):
        position = enemy.player.x, enemy.player.y
        visible = hypot(position[0] - enemy.x, position[1] - enemy.y) <= self.detection_radius
        if visible:
            self.last_seen = position
            self.destination = None
        return visible

    def search(self, enemy, dt):
        if self.last_seen is None:
            enemy.moving, enemy.visual_time = False, 0.0
            return

        if self.destination is None:
            self.set_destination(enemy, enemy.constrain_position(*self.last_seen))
        dx, dy = self.destination[0] - enemy.x, self.destination[1] - enemy.y
        distance = hypot(dx, dy)
        if distance <= EPSILON or self.travel_budget <= 0:
            angle, offset = tau * random(), self.search_radius * sqrt(random())
            x, y = enemy.constrain_position(self.last_seen[0] + offset * cos(angle),
                                            self.last_seen[1] + offset * sin(angle))
            self.set_destination(enemy, (x, y))
            dx, dy = x - enemy.x, y - enemy.y
            distance = hypot(dx, dy)
        self.travel_budget -= enemy.data['speed_kmph'] / 3.6 * dt
        enemy.approach(dx, dy, distance, dt)

    def set_destination(self, enemy, position):
        self.destination = position
        # Budget enough movement to go around a body when the direct path is occupied.
        self.travel_budget = hypot(position[0] - enemy.x, position[1] - enemy.y) + 2 * enemy.height
