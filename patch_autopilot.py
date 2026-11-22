"""Exercise the real player and enemies only during a Patch Desktop test."""

from math import pi

import pico2d

from enemy_spacing import is_free
from projectile import Projectile
from wave_data import GATES, RANGED


class PatchRound:
    checks = ('gates-open-and-enemies-cross', 'arena-loads', 'parry-moves-enemy',
              'beam-three-pulses', 'ranged-fires',
              'player-hit-flashes', 'enemies-stay-apart', 'walking-guard-blocks-side',
              'parry-reaches-incoming-bolt')

    def __init__(self, mode, report):
        self.mode = mode
        self.report = report
        self.index = 0
        self.age = 0.0
        self.enemy = None
        self.target_x = 0.0
        self.triggered = False
        self.beam = None
        self.hit_colors = []
        self.side_shot = None
        self.parry_shot = None
        self.saw_partial_entry = False
        self.gates_started_closed = all(mode.waves.gate_opening(gate) == 0 for gate in GATES)

    def write(self, result, detail=''):
        with self.report.open('a', encoding='utf-8') as report:
            report.write(f'{result} {self.checks[self.index]}{detail}\n')
        self.index += 1
        self.age = 0.0

    def spawn(self, kind, distance):
        self.mode.waves.single_mode = kind
        self.mode.waves.load()
        self.enemy = self.mode.enemies[0]
        player = self.mode.player
        self.enemy.x, self.enemy.y = player.constrain_position(player.x + distance, player.y)

    def update(self, dt):
        if self.index >= len(self.checks):
            return
        self.age += dt
        player = self.mode.player
        combat = player.combat
        if self.age > 8:
            self.write('fail', ': expected scene result did not occur')
            self.index = len(self.checks)
        elif self.index == 0:
            waves = self.mode.waves
            shown = [entry for entry in waves.queue if entry.visible > 0]
            if any(waves.gate_opening(entry.gate['id']) < 1 for entry in shown):
                self.write('fail', ': an enemy appeared in front of a closed gate')
                self.index = len(self.checks)
                return
            self.saw_partial_entry |= any(0 < entry.visible < 1 for entry in shown)
            if (not waves.pending and self.saw_partial_entry and self.gates_started_closed
                    and [gate for _, gate, _ in waves.spawn_log] == list(GATES) * 2):
                waves.load(4)
                player.y = 23.0
                player.pressed_keys.add(pico2d.SDLK_w)
                self.write('pass')
        elif self.index == 1 and self.age >= 1.15:
            if self.mode.arena.gate_cell and player.y > 26 and player.visual_motion == 'run':
                player.pressed_keys.clear()
                self.spawn('melee', 0)
                self.enemy.x += self.enemy.attack_distance(0) + .8
                combat.aim = 0
                self.write('pass')
        elif self.index == 2:
            if not self.triggered and self.enemy.state == 'windup' and self.enemy.age >= .48:
                self.triggered = True
                self.target_x = self.enemy.x
                combat.right_down()
            if self.enemy.state == 'stunned' and self.enemy.get_bb()[0] > self.target_x - self.enemy.width / 2 + .5:
                combat.right_up()
                self.write('pass')
        elif self.index == 3:
            if not self.beam and combat.state == 'free' and self.age > .25:
                combat.energy = 40
                combat.fire()
                self.beam = combat.beam
            if self.beam and not self.beam.active and self.beam.ticks == 3:
                if all(self.enemy.identifier in ids for ids in self.beam.hit_ids) and player.effects.sound:
                    self.spawn('ranged', 14)
                    self.write('pass')
        elif self.index == 4:
            if self.enemy.shots > 0 and self.enemy.x - player.x >= 13.9:
                self.write('pass')
        elif self.index == 5:
            color = player.effects.player_flash_color()
            if color is not None and (not self.hit_colors or color != self.hit_colors[-1]):
                self.hit_colors.append(color)
            if (combat.hp < combat.settings['player_hp'] and color is None
                    and self.hit_colors == ['red', 'white', 'red']):
                self.mode.waves.load(3, 'all')
                self.write('pass')
        elif self.index == 6:
            enemies = self.mode.enemies
            if any(not is_free(enemy, enemy.x, enemy.y) for enemy in enemies):
                self.write('fail', ': enemies moved inside the spacing gap')
            elif self.age >= 2 and len(enemies) == 16:
                self.mode.waves.load(4, 'all')
                combat.aim = -pi / 2
                combat.right_down()
                player.pressed_keys.add(pico2d.SDLK_d)
                self.write('pass')
        elif self.index == 7:
            if self.side_shot is None and combat.walking_guard():
                self.side_shot = Projectile('guard-side', player.x + 4, player.y, pi, RANGED['ranged'], player)
                self.mode.waves.add_projectile(self.side_shot)
            elif self.side_shot is not None and self.side_shot.result:
                if self.side_shot.result != 'block':
                    self.write('fail', ': side projectile was not blocked during guard walk')
                elif self.age >= 1.55:
                    player.pressed_keys.clear()
                    combat.right_up()
                    self.write('pass')
        elif self.index == 8:
            if self.parry_shot is None:
                combat.aim = 0
                combat.right_down()
                reach = combat.settings['parry_radius_m']
                self.parry_shot = Projectile('parry-distance', player.x + reach + 1, player.y,
                                             pi, RANGED['ranged'], player)
                self.mode.waves.add_projectile(self.parry_shot)
            elif self.parry_shot.result:
                gap = self.parry_shot.x - self.parry_shot.radius - player.get_bb()[2]
                if self.parry_shot.result == 'parry' and gap > 1:
                    self.write('pass')
                else:
                    self.write('fail', ': the projectile reached the body before being parried')
