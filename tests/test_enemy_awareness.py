import unittest
from itertools import cycle
from math import hypot
from unittest.mock import patch

from test_scale import scene
import game_framework
from combat_data import ENEMIES
from enemy import MeleeEnemy
from orc_boss import OrcBoss
from ranged_enemy import RangedEnemy
from wave_data import RANGED


class EnemyAwarenessTests(unittest.TestCase):
    def encounters(self):
        for kind in ('melee', 'ranged', 'boss'):
            arena, player, _ = scene()
            shots = []
            if kind == 'melee':
                enemy = MeleeEnemy(kind, ENEMIES['melee'], 0, 0, player)
            elif kind == 'ranged':
                enemy = RangedEnemy(kind, RANGED['ranged'], 0, 0, player, shots.append)
            else:
                enemy = OrcBoss(kind, player)
            player.targets = [enemy]
            yield arena, player, enemy, shots

    def test_detection_radius_is_two_fifths_of_arena_diameter(self):
        game_framework.frame_time = 1 / 120
        for arena, player, enemy, _ in self.encounters():
            with self.subTest(enemy=enemy.identifier):
                radius = 2 * arena.radius * 2 / 5
                player.x = radius + .001
                enemy.update()
                self.assertIsNone(enemy.awareness.last_seen)
                self.assertEqual((enemy.x, enemy.y), (0, 0))
                player.x = radius
                enemy.update()
                self.assertEqual(enemy.awareness.last_seen, (radius, 0))

    def test_searches_last_seen_position_before_wandering_and_reacquires(self):
        game_framework.frame_time = 1 / 120
        for _, player, enemy, shots in self.encounters():
            with self.subTest(enemy=enemy.identifier):
                enemy.x = -20
                player.x = -3
                enemy.update()
                last_seen = enemy.awareness.last_seen
                player.x = 32
                with patch('enemy_awareness.random', side_effect=cycle((0, .5, .25, .5))):
                    for _ in range(120 * 8):
                        enemy.update()
                        if enemy.awareness.destination != last_seen:
                            break
                    self.assertAlmostEqual(enemy.x, last_seen[0], delta=.03)
                    self.assertAlmostEqual(enemy.y, last_seen[1], delta=.03)
                    first_waypoint = enemy.awareness.destination
                    self.assertGreater(hypot(first_waypoint[0] - last_seen[0], first_waypoint[1]), 0)
                    self.assertLessEqual(hypot(first_waypoint[0] - last_seen[0], first_waypoint[1]), player.height)
                    for _ in range(120 * 3):
                        enemy.update()
                        if enemy.awareness.destination != first_waypoint:
                            break
                    self.assertNotEqual(enemy.awareness.destination, first_waypoint)
                self.assertEqual(enemy.awareness.last_seen, last_seen)
                self.assertEqual(enemy.attack_count, 0)
                self.assertFalse(shots)
                player.x, player.y = enemy.x + 1, enemy.y
                enemy.update()
                self.assertEqual(enemy.awareness.last_seen, (player.x, player.y))
                self.assertIsNone(enemy.awareness.destination)
