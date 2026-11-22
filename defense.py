"""입력 잠금, 패링, 기본 방어, 무적과 에너지를 분리한 전투 상태."""

from math import atan2, cos, hypot, pi, radians

from beam import Beam
from combat_data import STAGES, SYSTEMS
from geometry import draw_sector
from presentation_data import VISUALS


class PlayerCombat:
    def __init__(self, owner):
        self.owner = owner
        self.settings = SYSTEMS['main']
        self.hp = self.settings['player_hp']
        self.energy = 0
        self.state = 'free'
        self.time = 0.0
        self.aim = 0.0
        self.right_held = False
        self.started = 0.0
        self.window = 0.0
        self.success_invuln_until = 0.0
        self.hit_invuln_until = 0.0
        self.success = False
        self.stunned_one = False
        self.failure_reported = False
        self.parry_hit_at = None
        self.beam = None
        self.resolved = set()
        self.events = []
        self.message = 'READY'
        self.message_until = 0.0

    def stage(self):
        return next(row for row in reversed(list(STAGES.values()))
                    if self.energy >= row['energy_min'])

    def feedback(self, result):
        self.message = result.upper()
        self.message_until = self.time + .4
        self.events.append((self.time, result))

    def right_down(self):
        if self.right_held:
            return
        self.right_held = True
        if self.state not in ('free', 'guard'):
            return
        self.state = 'raising'
        self.started = self.time
        self.window = self.stage()['parry_window_s']
        self.success = False
        self.stunned_one = False
        self.failure_reported = False
        self.parry_hit_at = None

    def right_up(self):
        self.right_held = False
        if self.state == 'guard':
            self.state = 'free'

    def fire(self):
        if self.state not in ('free', 'guard') or self.energy <= 0:
            return False
        energy, stage = self.energy, self.stage()
        self.energy = 0
        self.state = 'beam'
        self.beam = Beam(self.owner, energy, stage, self.settings)
        if self.owner.effects:
            self.owner.effects.beam(stage['id'] == 'stage4')
        self.feedback('beam')
        return True

    def parry_frame(self):
        elapsed = self.time - self.started
        motion = VISUALS['parry']
        peak_at = motion['raise_s']
        if self.parry_hit_at is not None:
            peak_at = max(peak_at, self.parry_hit_at) + motion['success_hold_s']
            if elapsed <= peak_at:
                return 8
        elif elapsed <= peak_at:
            return 8 * (elapsed / peak_at) ** .75
        return 8 + 7 * min(1, (elapsed - peak_at) / motion['return_s'])

    def position_lock_remaining(self):
        if self.state != 'raising':
            return 0.0
        return max(0.0, self.settings['parry_move_lock_s'] - (self.time - self.started))

    def parry_active(self):
        return self.state == 'raising' and self.time - self.started < self.window - 1e-9

    def advance(self, dt):
        self.time += dt
        if self.state == 'raising':
            elapsed = self.time - self.started
            if not self.success and elapsed >= self.window and not self.failure_reported:
                self.feedback('miss')
                self.failure_reported = True
            if elapsed + 1e-9 >= self.settings['input_lock_s']:
                self.state = 'guard' if self.right_held else 'free'

    def update_beam(self, dt):
        if self.beam and self.beam.active:
            self.beam.update(dt)
        if self.state == 'beam' and not self.beam.active:
            self.state = 'free'

    def walking_guard(self):
        return self.state == 'guard' and self.owner.moving

    def guard_arc(self):
        setting = 'guard_walk_angle_deg' if self.walking_guard() else 'guard_angle_deg'
        return radians(self.settings[setting])

    def front(self, source):
        direction = getattr(source, 'incoming_angle',
                            atan2(source.y - self.owner.y, source.x - self.owner.x))
        delta = direction - self.aim
        return cos(delta) >= cos(self.guard_arc() / 2) - 1e-9

    def push_parried_enemies(self):
        left, bottom, right, top = self.owner.get_bb()
        reach = self.settings['parry_push_range_m']
        for enemy in self.owner.targets:
            if enemy.hp <= 0 or not self.front(enemy):
                continue
            x1, y1, x2, y2 = enemy.get_bb()
            dx = max(0.0, left - x2, x1 - right)
            dy = max(0.0, bottom - y2, y1 - top)
            if hypot(dx, dy) <= reach + 1e-9:
                enemy.start_parry_recoil()

    def receive(self, attack_id, source, damage, energy_gain):
        if self.hp <= 0 or attack_id in self.resolved:
            return 'ignored'
        self.resolved.add(attack_id)
        # 일반 피격 보호 중에는 새 패링으로 축적하지 않는다.
        if self.time < self.hit_invuln_until - 1e-9:
            return 'invulnerable'
        if self.parry_active() and self.front(source):
            self.energy = min(self.settings['energy_max'], self.energy + energy_gain)
            if not self.success:
                self.success_invuln_until = self.time + self.settings['success_invuln_s']
                self.parry_hit_at = self.time - self.started
                self.push_parried_enemies()
            self.success = True
            if not self.stunned_one and getattr(source, 'can_be_stunned', True):
                source.stun(self.settings['stun_s'])
                self.stunned_one = True
            self.feedback('parry')
            return 'parry'
        if self.time < self.success_invuln_until - 1e-9:
            return 'invulnerable'
        if self.state == 'guard' and self.front(source):
            self.feedback('block')
            return 'block'
        previous = self.hp
        self.hp = max(0, self.hp - damage)
        if self.owner.effects:
            self.owner.effects.damage(self.owner, previous - self.hp, player_hit=True)
        self.hit_invuln_until = self.time + self.settings['hit_invuln_s']
        self.feedback('hit')
        if self.hp == 0:
            self.state = 'dead'
            self.owner.pressed_keys.clear()
            self.beam = None
        return 'hit'

    def draw(self):
        raising = self.position_lock_remaining() > 1e-9
        if self.state == 'guard' or raising:
            color = (101, 185, 248) if self.state == 'guard' else (239, 166, 76)
            if self.parry_active():
                color = (111, 255, 169)
            if raising:
                radius = self.owner.height * VISUALS['parry']['indicator_height_ratio']
            else:
                radius = self.owner.height * .65 if self.walking_guard() else 1.5
            draw_sector(self.owner.x, self.owner.y, self.aim, radius,
                        self.guard_arc(), self.owner.camera, color)
        if self.time < self.success_invuln_until:
            draw_sector(self.owner.x, self.owner.y, 0, 1.2, 2 * pi,
                        self.owner.camera, (168, 249, 187))
