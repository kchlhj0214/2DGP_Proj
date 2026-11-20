"""방향을 고정한 뒤 회전하는 칼 히트박스로 한 번 공격하는 근접 적."""

from math import atan2, cos, hypot, pi, radians, sin

import pico2d

import game_framework
from game_data import CHARACTERS, VIEWPORTS
from geometry import box_points, draw_sector, intersects, oriented_box
from enemy_spacing import move_enemy, safe_step
from presentation_data import VISUALS
from sprites import clip_duration


class MeleeEnemy:
    sprite_actor = 'melee'
    death_action = 'collapse'

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
        self.recoil_age = None
        self.recoil_angle = 0.0
        self.visual_time = 0.0
        self.moving = False
        self.death_age = 0.0

    def get_bb(self):
        return (self.x - self.width / 2, self.y - self.height / 2,
                self.x + self.width / 2, self.y + self.height / 2)

    def stun(self, duration):
        if self.hp > 0:
            self.state, self.age = 'stunned', 0.0
            self.stun_duration = duration
            self.attack_id = None

    def start_parry_recoil(self):
        if self.sprite_actor != 'melee' or self.hp <= 0:
            return
        dx, dy = self.x - self.player.x, self.y - self.player.y
        self.recoil_angle = atan2(dy, dx) if dx or dy else self.angle + pi
        self.recoil_age = 0.0

    def advance_recoil(self, dt):
        if self.recoil_age is None:
            return
        settings = VISUALS['parry']
        duration = settings['push_s']
        old = min(1.0, self.recoil_age / duration)
        self.recoil_age += dt
        progress = min(1.0, self.recoil_age / duration)
        travel = self.height * settings['push_height_ratio'] * ((1 - old)**1.3 - (1 - progress)**1.3)
        safe_step(self, cos(self.recoil_angle) * travel, sin(self.recoil_angle) * travel)
        if self.recoil_age > duration + 1 / 16:
            self.recoil_age = None

    def take_damage(self, amount):
        if self.hp <= 0:
            return
        previous = self.hp
        self.hp = max(0, self.hp - amount)
        if self.player.effects:
            self.player.effects.damage(self, previous - self.hp)
        if self.hp == 0:
            self.state = 'dead'
            self.attack_id = None

    def walk_toward(self, dx, dy, dt):
        pos = (self.x, self.y)
        move_enemy(self, dx, dy)
        self.moving = hypot(self.x - pos[0], self.y - pos[1]) > 1e-9
        self.visual_time = self.visual_time + dt if self.moving else 0.0

    def sword_polygon(self):
        progress = min(1.0, self.age / self.data['swing_s'])
        spread = radians(self.data['sweep_deg'])
        angle = self.angle - spread / 2 + spread * progress
        return oriented_box(self.x, self.y, angle,
                            self.data['sword_length_m'], self.data['sword_width_m'])

    def resolve_sword(self):
        if not self.hit and intersects(self.sword_polygon(), box_points(self.player.get_bb())):
            self.hit = True
            self.player.combat.receive(self.attack_id, self, self.data['damage'], self.data['energy_gain'])

    def update(self):
        if self.hp <= 0:
            self.death_age += game_framework.frame_time
            return
        if self.player.combat.hp <= 0:
            return
        dt = game_framework.frame_time
        self.advance_recoil(dt)
        if self.state == 'chase':
            dx, dy = self.player.x - self.x, self.player.y - self.y
            distance = hypot(dx, dy)
            if distance > 0:
                self.angle = atan2(dy, dx)
            if distance > self.data['stop_m'] + 1e-9:
                step = min(distance - self.data['stop_m'], self.data['speed_kmph'] / 3.6 * dt)
                # 적의 발밑도 플레이어와 같은 원 경계를 사용한다.
                self.walk_toward(dx / distance * step, dy / distance * step, dt)
            else:
                self.state, self.age = 'windup', 0.0
                self.moving, self.visual_time = False, 0.0
            return
        self.age += dt
        if self.state == 'stunned':
            if self.age + 1e-9 >= self.stun_duration:
                self.state, self.age = 'chase', 0.0
            return
        if self.state == 'windup' and self.age + 1e-9 >= self.data['windup_s']:
            self.age = max(0.0, self.age - self.data['windup_s'])
            self.state = 'swing'
            self.attack_count += 1
            self.attack_id = (self.identifier, self.attack_count)
            self.hit = False
        if self.state == 'swing':
            self.resolve_sword()
            if self.state == 'swing' and self.age + 1e-9 >= self.data['swing_s']:
                self.state, self.age = 'recovery', 0.0
        elif self.state == 'recovery' and self.age + 1e-9 >= self.data['recovery_s']:
            self.state, self.age = 'chase', 0.0

    def pose(self):
        if self.recoil_age is not None:
            return 'deflected', self.recoil_age / VISUALS['parry']['push_s'] * 12
        if self.state == 'windup':
            return 'chop', 6 * self.age / self.data['windup_s']
        if self.state == 'swing':
            frame = 6 + 3 * self.age / self.data['swing_s']
            return 'chop', max(8, frame) if self.hit else frame
        if self.state == 'recovery':
            return 'chop', 9 + 6 * self.age / self.data['recovery_s']
        return ('walk' if self.moving and self.state == 'chase' else 'idle'), None

    def draw(self):
        flash = self.player.effects and self.player.effects.flashing(self)
        if not self.player.sprites:
            return
        camera = self.player.camera
        if self.hp <= 0:
            if self.death_age < clip_duration(self.sprite_actor, self.death_action):
                self.player.sprites.draw(self.sprite_actor, self.death_action, self, camera,
                                         self.angle, self.death_age, flash=flash)
            return
        if self.sprite_actor == 'melee' and self.state == 'windup' and self.recoil_age is None:
            draw_sector(self.x, self.y, self.angle, self.data['sword_length_m'],
                        radians(self.data['sweep_deg']), camera, (216, 138, 70))
        motion, frame = self.pose()
        self.player.sprites.draw(self.sprite_actor, motion, self, camera, self.angle,
                                 self.visual_time, frame, flash)
        if 0 < self.hp < self.data['hp']:
            left, _, right, top = self.get_bb()
            x1, y = camera.to_screen(left, top)
            x2, _ = camera.to_screen(right, top)
            pico2d.draw_rectangle(x1, y + 3, x2, y + 6, 64, 40, 43, filled=True)
            pico2d.draw_rectangle(x1, y + 3, x1 + (x2 - x1) * self.hp / self.data['hp'],
                                  y + 6, 237, 116, 113, filled=True)
