"""네 방향 동시 출현 대기열과 키보드 디버그 웨이브 전환."""

from collections import deque

import game_framework
import game_world
from combat_data import ENEMIES
from enemy import MeleeEnemy
from ranged_enemy import RangedEnemy
from wave_data import GATES, MODES, RANGED, SETTINGS, SINGLE_MODES, WAVES
from enemy_spacing import spawn_position


class WaveManager:
    def __init__(self, player, enemies, projectiles):
        self.player, self.enemies, self.projectiles = player, enemies, projectiles
        self.number = 1
        self.selection = 'all'
        self.single_mode = None
        self.elapsed = 0.0
        self.generation = 0
        self.queue = deque()
        self.spawn_log = []

    @property
    def pending(self):
        return len(self.queue)

    def add_projectile(self, projectile):
        self.projectiles.append(projectile)
        game_world.add_object(projectile, 1)

    def load(self, number=None, selection=None):
        if number is not None or selection is not None:
            self.single_mode = None
        if number is not None:
            self.number = number
        if selection is not None:
            self.selection = selection
        wave = next(row for row in WAVES.values() if row['number'] == self.number)
        # 객체 목록을 제자리에서 비워 광선/플레이어가 이전 목록을 참조하지 않게 한다.
        for obj in self.enemies + self.projectiles:
            game_world.remove_object(obj)
        self.enemies.clear()
        self.projectiles.clear()
        self.queue.clear()
        self.spawn_log.clear()
        self.elapsed = 0.0
        self.generation += 1
        kinds = ([wave['melee_id']] * wave['melee_per_gate']
                 + [wave['ranged_id']] * wave['ranged_per_gate'])
        if self.selection != 'all':
            kinds = [wave[f'{self.selection}_id']] * len(kinds)
        if self.single_mode is not None:
            row = SINGLE_MODES[self.single_mode]
            if row['count']:
                self.queue.append((0, GATES['north'], row['enemy_id']))
        else:
            for index, kind in enumerate(kinds):
                for gate in GATES.values():
                    self.queue.append((index * SETTINGS['main']['spawn_interval_s'], gate, kind))
        # 네 방향의 첫 적은 즉시 동시에 출현하며 별도 예고는 없다.
        self.spawn_due()

    def spawn_due(self):
        while self.queue and self.queue[0][0] <= self.elapsed + 1e-9:
            time, gate, kind = self.queue.popleft()
            x, y = self.player.constrain_position(gate['x_ratio'] * self.player.arena.radius,
                                                   gate['y_ratio'] * self.player.arena.radius)
            identifier = f'{self.generation}:{gate["id"]}:{len(self.spawn_log)}'
            if kind in ENEMIES:
                enemy = MeleeEnemy(identifier, ENEMIES[kind], x, y, self.player)
            else:
                enemy = RangedEnemy(identifier, RANGED[kind], x, y, self.player, self.add_projectile)
            enemy.x, enemy.y = spawn_position(enemy, x, y)
            self.enemies.append(enemy)
            game_world.add_object(enemy, 1)
            self.spawn_log.append((time, gate['id'], kind))

    def handle_key(self, key):
        if key == ord('q'):
            modes = list(SINGLE_MODES)
            index = modes.index(self.single_mode) if self.single_mode is not None else -1
            self.single_mode = modes[(index + 1) % len(modes)]
            self.load()
            return True
        # pico2d의 숫자 키는 ASCII 코드이므로 키패드와 구분해 처리한다.
        for row in WAVES.values():
            if key == ord(str(row['number'])):
                self.load(number=row['number'])
                return True
        for row in MODES.values():
            if key == ord(str(row['key'])):
                self.load(selection=row['id'])
                return True
        return False

    def update(self):
        if self.player.combat.hp > 0:
            self.elapsed += game_framework.frame_time
            self.spawn_due()

    def draw(self):
        pass
