"""Exercise the real player and enemies only during a Patch Desktop test."""

import pico2d


class PatchRound:
    checks = ('arena-loads', 'parry-moves-enemy', 'beam-three-pulses', 'ranged-fires')

    def __init__(self, mode, report):
        self.mode = mode
        self.report = report
        self.index = 0
        self.age = 0.0
        self.enemy = None
        self.target_x = 0.0
        self.triggered = False
        self.beam = None
        self.mode.waves.load(4)
        self.mode.player.y = 23.0
        self.mode.player.pressed_keys.add(pico2d.SDLK_w)

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
            self.write('fail', ': expected combat result did not occur')
            self.index = len(self.checks)
        elif self.index == 0 and self.age >= 1.15:
            if len(self.mode.arena.art) == 2 and player.y > 26 and player.visual_motion == 'run':
                player.pressed_keys.clear()
                self.spawn('melee', 1.6)
                self.target_x = self.enemy.x
                combat.aim = 0
                self.write('pass')
        elif self.index == 1:
            if not self.triggered and self.enemy.state == 'windup' and self.enemy.age >= .48:
                self.triggered = True
                combat.right_down()
            if self.enemy.state == 'stunned' and self.enemy.get_bb()[0] > self.target_x - self.enemy.width / 2 + .5:
                combat.right_up()
                self.write('pass')
        elif self.index == 2:
            if not self.beam and combat.state == 'free' and self.age > .25:
                combat.energy = 40
                combat.fire()
                self.beam = combat.beam
            if self.beam and not self.beam.active and self.beam.ticks == 3:
                if all(self.enemy.identifier in ids for ids in self.beam.hit_ids) and player.effects.sound:
                    self.spawn('ranged', 5)
                    self.write('pass')
        elif self.index == 3:
            if self.enemy.shots > 0 and combat.hp < combat.settings['player_hp'] and self.age >= 1.5:
                self.write('pass')
