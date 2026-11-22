"""철창과 다리의 출현 타임라인 및 키보드 디버그 웨이브 전환."""

from collections import deque
from dataclasses import dataclass
from math import atan2

import game_framework
import game_world
from combat_data import ENEMIES
from enemy import MeleeEnemy
from presentation_data import VISUALS
from ranged_enemy import RangedEnemy
from wave_data import GATES, MODES, RANGED, SETTINGS, SINGLE_MODES, WAVES
from enemy_spacing import is_free, spawn_position


ENTRY = SETTINGS['main']


@dataclass
class BridgeEntry:
    enemy: MeleeEnemy
    gate: dict
    kind: str
    passage_at: float
    arrival_at: float
    visible: float = 0.0
    landing: tuple | None = None

    def advance(self, elapsed, portal_distance, choose_landing):
        travel = (elapsed - self.passage_at) * ENTRY['entrance_speed_mps']
        distance = portal_distance - travel
        enemy = self.enemy
        dx, dy = self.gate['x_ratio'], self.gate['y_ratio']
        enemy.x = dx * distance
        enemy.y = dy * distance + enemy.height / 2
        inside = travel - ENTRY['portal_offset_m']
        if inside >= 0:
            if self.landing is None:
                self.landing = choose_landing(enemy, self.gate)
            span = ENTRY['bridge_inset_m']
            fraction = min(1.0, inside / span)
            end = portal_distance - ENTRY['portal_offset_m'] - span
            enemy.x += (self.landing[0] - dx * end) * fraction
            enemy.y += (self.landing[1] - dy * end - enemy.height / 2) * fraction
        self.enemy.visual_time = max(0.0, elapsed - self.passage_at)
        self.visible = min(1.0, max(0.0, travel / ENTRY['reveal_m']))

    def draw(self):
        enemy = self.enemy
        if self.visible > 0 and enemy.player.sprites:
            enemy.player.sprites.draw(enemy.sprite_actor, 'walk', enemy, enemy.player.camera,
                                      enemy.angle, enemy.visual_time, reveal=self.visible)


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
        self.gate_lifts = {}
        self.overview_until = 0.0

    @property
    def portal_distance(self):
        return self.player.arena.radius + ENTRY['portal_offset_m']

    def gate_opening(self, gate_id):
        if gate_id not in self.gate_lifts:
            return 0.0
        return min(1.0, max(0.0, (self.elapsed - self.gate_lifts[gate_id]) / ENTRY['gate_lift_s']))

    def camera_zoom(self):
        art = VISUALS['arena']
        blend = min(1.0, max(0.0, (self.elapsed - self.overview_until) / art['overview_return_s']))
        if not self.overview_until or blend >= 1.0:
            return 1.0
        camera = self.player.camera
        span_y = self.portal_distance * camera.floor_y_ratio + art['gate_height_m'] + 3.7
        span_x = self.portal_distance + art['bridge_width_m']
        initial = min(camera.height_m / (2 * span_y), camera.width_m / (2 * span_x), 1.0)
        smooth = blend * blend * (3.0 - 2.0 * blend)
        return initial + (1.0 - initial) * smooth

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
        self.gate_lifts.clear()
        self.overview_until = 0.0
        self.elapsed = 0.0
        self.generation += 1
        kinds = ([wave['melee_id']] * wave['melee_per_gate']
                 + [wave['ranged_id']] * wave['ranged_per_gate'])
        if self.selection != 'all':
            kinds = [wave[f'{self.selection}_id']] * len(kinds)
        if self.single_mode is not None:
            row = SINGLE_MODES[self.single_mode]
            if row['count']:
                gate = GATES['north']
                self.gate_lifts['north'] = -ENTRY['gate_lift_s']
                self.activate(self.make_enemy(gate, row['enemy_id'], 0), gate, row['enemy_id'], 0)
        elif kinds:
            gap = ENTRY['arrival_interval_s']
            travel_time = (ENTRY['portal_offset_m'] + ENTRY['bridge_inset_m']) / ENTRY['entrance_speed_mps']
            self.gate_lifts = {gate_id: ENTRY['gate_wait_s'] + index * gap
                               for index, gate_id in enumerate(GATES)}
            for index, kind in enumerate(kinds):
                for gate in GATES.values():
                    passage = self.gate_lifts[gate['id']] + ENTRY['gate_lift_s'] + index * len(GATES) * gap
                    enemy = self.make_enemy(gate, kind, index)
                    entry = BridgeEntry(enemy, gate, kind, passage, passage + travel_time)
                    entry.advance(0, self.portal_distance, self.choose_landing)
                    self.queue.append(entry)
            if abs(self.player.x) + abs(self.player.y) < self.player.arena.radius / 4:
                self.overview_until = self.queue[-1].arrival_at

    def make_enemy(self, gate, kind, index):
        identifier = f'{self.generation}:{gate["id"]}:{index}'
        if kind in ENEMIES:
            enemy = MeleeEnemy(identifier, ENEMIES[kind], 0, 0, self.player)
        else:
            enemy = RangedEnemy(identifier, RANGED[kind], 0, 0, self.player, self.add_projectile)
        enemy.angle = atan2(-gate['y_ratio'], -gate['x_ratio'])
        return enemy

    def choose_landing(self, enemy, gate):
        distance = self.player.arena.radius - ENTRY['bridge_inset_m']
        dx, dy = gate['x_ratio'], gate['y_ratio']
        x, y = dx * distance, dy * distance + enemy.height / 2
        side_gap = (enemy.height if dx else enemy.width) + ENTRY['enemy_gap_m'] + 0.1
        for side in (0, 1, -1, 2, -2):
            candidate = self.player.constrain_position(x - dy * side * side_gap,
                                                       y + dx * side * side_gap)
            if is_free(enemy, *candidate):
                return candidate
        return spawn_position(enemy, x, y)

    def activate(self, enemy, gate, kind, time, landing=None):
        if landing is None or not is_free(enemy, *landing):
            landing = self.choose_landing(enemy, gate)
        enemy.x, enemy.y = landing
        enemy.moving = time > 0
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
            while self.queue and self.queue[0].arrival_at <= self.elapsed + 1e-9:
                entry = self.queue.popleft()
                entry.advance(entry.arrival_at, self.portal_distance, self.choose_landing)
                self.activate(entry.enemy, entry.gate, entry.kind, entry.arrival_at, entry.landing)
            for entry in self.queue:
                entry.advance(self.elapsed, self.portal_distance, self.choose_landing)

    def draw(self):
        self.player.arena.draw_gates(self)
        for entry in sorted(self.queue, key=lambda item: item.enemy.y, reverse=True):
            entry.draw()
        self.player.arena.draw_gates(self, foreground=True)
