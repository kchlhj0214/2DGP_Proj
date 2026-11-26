"""Exercise the real player and enemies only during a Patch Desktop test."""

from math import pi

import pico2d

from enemy_spacing import is_free
from orc_boss import CHARGE, ROCK
from projectile import Projectile
from wave_data import GATES, RANGED, SETTINGS


class PatchRound:
    stages = ('arena-and-entrances', 'arena-and-entrances', 'parry-moves-enemy',
              'beam-three-pulses-heals', 'ranged-fires',
              'player-hit-flashes', 'enemies-stay-apart', 'walking-guard-blocks-side',
              'parry-reaches-incoming-bolt', 'waves-advance-and-carry', 'waves-advance-and-carry',
              'boss-charge-stops-on-parry', 'boss-slam-drops-rocks', 'boss-sweep-shoves-guard')
    checks = tuple(dict.fromkeys(stages))

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
        self.started_wave_check = False
        self.carry_enemies = ()
        self.boss_attack_started = False
        self.boss_hit_seen = False
        self.boss_hp_before_attack = 0

    def write(self, result, detail=''):
        name = self.stages[self.index]
        if result == 'fail' or name not in self.stages[self.index + 1:]:
            with self.report.open('a', encoding='utf-8') as report:
                report.write(f'{result} {name}{detail}\n')
        self.index = len(self.stages) if result == 'fail' else self.index + 1
        self.age = 0.0

    def spawn(self, kind, distance):
        self.mode.waves.single_mode = kind
        self.mode.waves.load()
        self.enemy = self.mode.enemies[0]
        player = self.mode.player
        self.enemy.x, self.enemy.y = player.constrain_position(player.x + distance, player.y)

    def update(self, dt):
        if self.index >= len(self.stages):
            return
        self.age += dt
        player = self.mode.player
        combat = player.combat
        if self.age > 8:
            self.write('fail', ': expected scene result did not occur')
        elif self.index == 0:
            waves = self.mode.waves
            shown = [entry for entry in waves.queue if entry.visible > 0]
            if any(waves.gate_opening(entry.gate['id']) < 1 for entry in shown):
                self.write('fail', ': an enemy appeared in front of a closed gate')
                return
            self.saw_partial_entry |= any(0 < entry.visible < 1 for entry in shown)
            if (not waves.pending and self.saw_partial_entry and self.gates_started_closed
                    and [gate for _, gate, _ in waves.spawn_log] == list(GATES) * 2):
                waves.single_mode = 'none'
                waves.load()
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
            full_health = combat.settings['player_hp']
            if not self.beam and combat.state == 'free' and self.age > .25:
                combat.energy = 40
                combat.hp = full_health - combat.settings['heal_per_kill']
                combat.fire()
                self.beam = combat.beam
            if self.beam and not self.beam.active and self.beam.ticks == 3:
                if (all(self.enemy.identifier in ids for ids in self.beam.hit_ids)
                        and self.enemy.hp == 0 and combat.hp == full_health and player.effects.sound):
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
                self.mode.waves.single_mode = 'none'
                self.mode.waves.load()
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
        elif self.index == 9:
            waves = self.mode.waves
            limit = SETTINGS['main']['time_limit_s']
            if not self.started_wave_check:
                player.x = player.y = 0.0
                waves.load(1, 'all')
                self.started_wave_check = True
            elif waves.number == 2 and limit - .1 < waves.remaining_s <= limit:
                # Cross the real deadline without holding the desktop test open for two minutes.
                waves.elapsed = limit - .5
                self.write('pass')
            elif waves.number == 1 and not waves.pending and 0 < waves.remaining_s < limit:
                for enemy in self.mode.enemies:
                    enemy.take_damage(enemy.hp)
        elif self.index == 10:
            waves = self.mode.waves
            limit = SETTINGS['main']['time_limit_s']
            if waves.number == 2 and self.mode.enemies and not self.carry_enemies:
                self.carry_enemies = tuple(self.mode.enemies)
            elif (waves.number == 3 and limit - .1 < waves.remaining_s <= limit
                  and self.carry_enemies and all(enemy in self.mode.enemies for enemy in self.carry_enemies)
                  and waves.pending == 16 and combat.hp > 0):
                waves.load(4, 'all')
                player.x, player.y = 6.0, 0.0
                player.pressed_keys.clear()
                combat.aim, combat.energy = pi, 0
                combat.hp = combat.settings['player_hp']
                combat.right_up()
                self.write('pass')
        elif self.index >= 11:
            self.boss_round()

    def boss_round(self):
        player, boss = self.mode.player, self.mode.waves.boss
        if boss is None:
            return
        combat = player.combat
        if self.index == 11:
            if boss.state == 'windup' and boss.age >= CHARGE['windup_s'] - .12:
                combat.right_down()
            if boss.staggered and boss.state == 'recovery' and combat.energy == combat.settings['energy_max'] / 2:
                combat.right_up()
                self.write('pass')
        elif self.index == 12:
            if combat.state == 'free':
                combat.right_down()
            if boss.state == 'idle' and combat.state == 'guard' and not self.boss_attack_started:
                self.boss_attack_started = True
                self.boss_hp_before_attack = combat.hp
                boss.begin('slam')
            if boss.state == 'rocks':
                self.boss_hit_seen |= len(boss.rocks) == ROCK['count'] and combat.hp < self.boss_hp_before_attack
            if boss.pattern == 'slam' and boss.state == 'recovery' and self.boss_hit_seen:
                self.boss_attack_started = False
                self.write('pass')
        elif self.index == 13:
            if boss.state == 'idle' and not self.boss_attack_started:
                self.boss_attack_started = True
                player.x, player.y = boss.x + 6, boss.y
                self.target_x = player.x
                self.boss_hp_before_attack = combat.hp
                boss.begin('swing')
            if self.boss_attack_started and player.x - self.target_x >= self.mode.arena.radius / 2 - .01:
                if combat.hp == self.boss_hp_before_attack:
                    self.write('pass')
                else:
                    self.write('fail', ': guarding the swing should prevent all HP loss')
