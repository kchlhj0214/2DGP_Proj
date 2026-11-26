"""Undead orc boss: locked charge, club sweep and two-stage ground slam."""

from dataclasses import dataclass
from math import atan2, cos, hypot, pi, radians, sin, sqrt
from random import Random

import game_framework
from boss_data import BOSSES, CHARGES, ROCKS, SLAMS, SWINGS
from enemy import MeleeEnemy
from geometry import (box_points, circle_intersects_polygon, circle_points, draw_boss_warning,
                      draw_sweep_warning, intersects, oriented_box)


BOSS = BOSSES['orc']
CHARGE, SLAM, ROCK, SWING = (table['main'] for table in (CHARGES, SLAMS, ROCKS, SWINGS))
ATTACKS = {'charge': CHARGE, 'slam': SLAM, 'swing': SWING}
PATTERNS = ('charge', 'swing', 'slam', 'swing')


@dataclass
class FallingRock:
    x: float
    y: float
    impact_at: float
    spent: bool = False
    can_be_stunned = False
    incoming_angle: float = 0.0


class OrcBoss(MeleeEnemy):
    sprite_actor = 'boss'
    death_action = 'collapse'
    can_be_stunned = False

    def __init__(self, identifier, player):
        super().__init__(identifier, BOSS, 0.0, 0.0, player)
        self.width *= BOSS['scale']
        self.height *= BOSS['scale']
        self.state = 'idle'
        self.pattern = 'charge'
        self.next_pattern = 0
        self.charge_remaining = 0.0
        self.staggered = False
        self.rocks = []

    def constrain_position(self, x, y):
        offset = self.height / 4
        px, py = self.player.arena.constrain_box(x, y - offset, self.width, 2 * offset)
        return px, py + offset

    def start_parry_recoil(self):
        # Only a direct charge parry interrupts the orc.
        pass

    def take_damage(self, amount):
        super().take_damage(amount)
        if self.hp == 0:
            self.rocks.clear()

    def begin(self, pattern):
        self.pattern, self.state, self.age = pattern, 'windup', 0.0
        self.attack_count += 1
        self.attack_id = (self.identifier, self.attack_count)
        self.hit = False
        self.staggered = False
        self.moving, self.visual_time = False, 0.0
        if pattern == 'charge':
            self.charge_remaining = self.charge_distance()

    def charge_distance(self):
        ux, uy = cos(self.angle), sin(self.angle)
        low, high = 0.0, CHARGE['length_m']
        for _ in range(16):
            step = (low + high) / 2
            if self.player.arena.contains_box(self.x + ux * step, self.y - self.height / 4 + uy * step,
                                              self.width, self.height / 2):
                low = step
            else:
                high = step
        return low

    def hit_shape(self, shape, spec, source=None, attack_id=None, push=0.0):
        source = self if source is None else source
        attack_id = self.attack_id if attack_id is None else attack_id
        player = self.player
        combat = player.combat
        energy = combat.settings['energy_max'] * spec['energy_ratio']
        if shape(box_points(player.get_bb())):
            return combat.receive(attack_id, source, spec['damage'], energy,
                                  guard_damage_ratio=spec.get('guard_damage_ratio', 0),
                                  guard_push_m=push, guard_push_s=BOSS['push_s'])
        area = combat.parry_area(source)
        if area and shape(area) and combat.try_parry(attack_id, source, energy):
            return 'parry'
        return None

    def charge_shape(self, distance):
        # The leading shoulder remains active throughout the charge.
        return oriented_box(self.x, self.y, self.angle, distance + self.width / 2, CHARGE['width_m'])

    def charge_step(self, dt):
        distance = min(self.charge_remaining, CHARGE['speed_mps'] * dt)
        if not self.hit:
            path = self.charge_shape(distance)
            result = self.hit_shape(lambda points: intersects(path, points), CHARGE, push=CHARGE['guard_push_m'])
            self.hit = result is not None
            if result == 'parry':
                self.staggered = True
                self.recover()
                return
        self.x += cos(self.angle) * distance
        self.y += sin(self.angle) * distance
        self.charge_remaining -= distance
        self.visual_time += dt
        if self.charge_remaining <= 1e-9:
            self.recover()

    def slam(self):
        result = self.hit_shape(lambda points: circle_intersects_polygon(self.x, self.y, SLAM['radius_m'], points), SLAM)
        if result == 'parry':
            self.recover()
            return
        rng = Random(self.attack_count)
        player = self.player
        edge = player.arena.radius - ROCK['radius_m']
        # At least one drop threatens the player's current area; other drops cover the arena.
        radius = hypot(player.x, player.y)
        factor = min(1.0, edge / max(radius, 0.01))
        self.rocks = [FallingRock(player.x * factor, player.y * factor, ROCK['flight_s'])]
        for _ in range(ROCK['count'] * 20):
            if len(self.rocks) == ROCK['count']:
                break
            angle, distance = rng.random() * 2 * pi, edge * sqrt(rng.random())
            x, y = cos(angle) * distance, sin(angle) * distance
            if any(hypot(rock.x - x, rock.y - y) < ROCK['radius_m'] * 2 for rock in self.rocks):
                continue
            self.rocks.append(FallingRock(x, y, ROCK['flight_s'] + len(self.rocks) * ROCK['interval_s']))
        self.state, self.age = 'rocks', 0.0

    def drop_rocks(self):
        for index, rock in enumerate(self.rocks):
            if not rock.spent and self.age >= rock.impact_at:
                rock.spent = True
                dx, dy = rock.x - self.player.x, rock.y - self.player.y
                rock.incoming_angle = atan2(dy, dx) if dx or dy else self.player.combat.aim
                self.hit_shape(lambda points: circle_intersects_polygon(rock.x, rock.y, ROCK['radius_m'], points),
                               ROCK, source=rock, attack_id=(*self.attack_id, index))
        if all(rock.spent for rock in self.rocks):
            self.rocks.clear()
            self.recover()

    def swing(self):
        if not self.hit:
            progress = min(1.0, self.age / SWING['swing_s'])
            angle = self.angle + radians(SWING['spread_deg']) * (0.5 - progress)
            club = oriented_box(self.x, self.y, angle, SWING['length_m'], SWING['width_m'])
            push = 2 * self.player.arena.radius * SWING['guard_push_diameter_ratio']
            self.hit = self.hit_shape(lambda points: intersects(club, points), SWING, push=push) is not None
        if self.age >= SWING['swing_s']:
            self.recover()

    def recover(self):
        self.state, self.age, self.moving = 'recovery', 0.0, False

    def update(self):
        dt = game_framework.frame_time
        if self.hp <= 0:
            self.death_age += dt
            return
        if self.player.combat.hp <= 0:
            return
        self.age += dt
        if self.state == 'idle':
            dx, dy = self.player.x - self.x, self.player.y - self.y
            distance = hypot(dx, dy)
            if distance > 1e-9:
                self.angle = atan2(dy, dx)
            next_pattern = PATTERNS[self.next_pattern]
            if self.age >= BOSS['between_attacks_s']:
                if next_pattern != 'swing' or distance <= SWING['length_m']:
                    self.next_pattern = (self.next_pattern + 1) % len(PATTERNS)
                    self.begin(next_pattern)
                elif self.age >= BOSS['between_attacks_s'] + 1.5:
                    self.next_pattern = (self.next_pattern + 1) % len(PATTERNS)
                    self.begin('charge')
                elif distance:
                    stride = BOSS['speed_kmph'] / 3.6 * dt
                    self.walk_toward(dx / distance * stride, dy / distance * stride, dt)
        elif self.state == 'windup' and self.age >= ATTACKS[self.pattern]['windup_s']:
            self.state, self.age = self.pattern, 0.0
            if self.pattern == 'slam':
                self.slam()
            elif self.pattern == 'swing':
                self.swing()
        elif self.state == 'charge':
            self.charge_step(dt)
        elif self.state == 'swing':
            self.swing()
        elif self.state == 'rocks':
            self.drop_rocks()
        elif self.state == 'recovery' and self.age >= ATTACKS[self.pattern]['recovery_s']:
            self.state, self.age, self.visual_time = 'idle', 0.0, 0.0

    def pose(self):
        if self.state == 'windup':
            return self.pattern, min(3, 4 * self.age / ATTACKS[self.pattern]['windup_s'])
        if self.state == 'charge':
            return 'charge', 4 + int(self.visual_time * 13) % 4
        if self.state == 'swing':
            return 'swing', 4 + 3 * min(1.0, self.age / SWING['swing_s'])
        if self.state == 'rocks':
            return 'slam', min(7, 4 + self.age * 11)
        if self.state == 'recovery':
            if self.pattern == 'charge':
                action = 'stagger' if self.staggered else 'recover'
                return action, 7 * self.age / CHARGE['recovery_s']
            progress = self.age / ATTACKS[self.pattern]['recovery_s']
            return self.pattern, 7 if progress < .45 else 1 if progress < .7 else 0
        return ('walk' if self.moving else 'idle'), None

    def draw_warning(self):
        camera = self.player.camera
        if self.state == 'windup':
            strength = 0.48 + 0.48 * min(1, self.age / ATTACKS[self.pattern]['windup_s'])
            if self.pattern == 'charge':
                draw_boss_warning(self.charge_shape(self.charge_remaining), camera, strength)
            elif self.pattern == 'slam':
                draw_boss_warning(circle_points(self.x, self.y, SLAM['radius_m']), camera, strength)
            else:
                draw_sweep_warning(self.x, self.y, self.angle, SWING['length_m'], SWING['width_m'],
                                   radians(SWING['spread_deg']), camera, strength)
        elif self.state == 'rocks':
            for rock in self.rocks:
                if not rock.spent:
                    draw_boss_warning(circle_points(rock.x, rock.y, ROCK['radius_m']), camera,
                                      0.85 if rock.impact_at - self.age < .3 else .45)

    def draw(self):
        super().draw()
        sprites = self.player.sprites
        if sprites and self.state == 'rocks':
            camera = self.player.camera
            for rock in self.rocks:
                if not rock.spent:
                    progress = self.age / rock.impact_at
                    x, y = camera.to_screen(self.x + (rock.x - self.x) * progress,
                                            self.y + (rock.y - self.y) * progress)
                    lift = 11 * camera.pixels_per_meter * sin(pi * progress)
                    size = 1.8 * camera.pixels_per_meter
                    sprites.boss_rock.draw(x, y + lift, size, size)
