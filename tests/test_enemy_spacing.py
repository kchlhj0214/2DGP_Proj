"""피격 간격과 출현/이동/경계에서 적 몸체 겹침 방지 검사."""

import unittest

from test_scale import ROOT, capture_png, scene
import pico2d
import game_framework
import game_world
import play_mode
from combat_data import ENEMIES
from enemy import MeleeEnemy
from enemy_spacing import move_enemy, overlaps, spawn_position
from ranged_enemy import RangedEnemy
from wave_data import RANGED
from wave_manager import WaveManager


class SpacingTests(unittest.TestCase):
    def tearDown(self):
        game_world.clear()

    def actors(self):
        arena, player, camera = scene()
        first = MeleeEnemy('first', ENEMIES['melee'], 0, 0, player)
        second = RangedEnemy('second', RANGED['ranged'], first.width + .8, 0, player, lambda p: None)
        player.targets = [first, second]
        return player, first, second

    def assert_separate(self, enemies):
        live = [enemy for enemy in enemies if enemy.hp > 0]
        for index, enemy in enumerate(live):
            for other in live[index + 1:]:
                self.assertFalse(overlaps(enemy, enemy.x, enemy.y, other),
                                 f'{enemy.identifier} / {other.identifier}')
            foot_height = enemy.player.boundary_height
            foot_offset = (enemy.height - foot_height) / 2
            self.assertTrue(enemy.player.arena.contains_box(enemy.x, enemy.y - foot_offset,
                                                            enemy.width, foot_height))

    def test_second_damage_at_half_second_without_extending_immunity(self):
        player, first, second = self.actors()
        combat = player.combat
        self.assertEqual(combat.settings['hit_invuln_s'], .5)
        self.assertEqual(combat.receive('one', second, 10, 10), 'hit')
        until = combat.hit_invuln_until
        combat.advance(.499)
        self.assertEqual(combat.receive('two', second, 10, 10), 'invulnerable')
        self.assertEqual(combat.hp, 90)
        self.assertEqual(combat.hit_invuln_until, until)
        combat.advance(.001)
        self.assertEqual(combat.receive('three', second, 10, 10), 'hit')
        self.assertEqual(combat.hp, 80)
        self.assertEqual(combat.energy, 0)

    def test_large_move_cannot_tunnel_through_enemy(self):
        player, first, second = self.actors()
        move_enemy(first, 5, 0)
        self.assertLessEqual(first.x, second.x - (first.width + second.width)/2 + 1e-6)
        self.assert_separate([first, second])

    def test_stunned_enemy_stays_put_and_dead_enemy_does_not_block(self):
        player, first, second = self.actors()
        first.stun(1.5)
        position = first.x, first.y
        move_enemy(second, -5, 0)
        self.assertEqual((first.x, first.y), position)
        self.assert_separate([first, second])
        second.take_damage(60)
        move_enemy(first, 5, 0)
        self.assertAlmostEqual(first.x, 5)

    def test_blocked_spawn_keeps_timing_and_finds_space(self):
        arena, player, camera = scene()
        waves = WaveManager(player, player.targets, player.projectiles)
        waves.load(3, 'all')
        game_framework.frame_time = .9
        waves.update()  # 기존 적이 전혀 움직이지 않아도 다음 적은 겹치지 않는다.
        self.assertEqual((len(player.targets), waves.pending), (16, 0))
        self.assert_separate(player.targets)
        for gate in ('north', 'south', 'west', 'east'):
            times = [round(t, 6) for t, g, _ in waves.spawn_log if g == gate]
            self.assertEqual(times, [0, .3, .6, .9])

    def test_mixed_crowd_near_each_circular_boundary(self):
        arena, player, camera = scene()
        for x, y in ((0, arena.radius), (0, -arena.radius), (arena.radius, 0), (-arena.radius, 0)):
            player.targets.clear()
            for index in range(8):
                if index % 2:
                    enemy = RangedEnemy(str(index), RANGED['ranged'], x, y, player, lambda p: None)
                else:
                    enemy = MeleeEnemy(str(index), ENEMIES['melee'], x, y, player)
                enemy.x, enemy.y = spawn_position(enemy, x, y)
                player.targets.append(enemy)
            self.assert_separate(player.targets)
            for _ in range(120):
                for enemy in player.targets:
                    move_enemy(enemy, -enemy.x / 100, -enemy.y / 100)
                self.assert_separate(player.targets)

    def test_chasing_all_modes_stays_separate_over_time(self):
        for selection in ('all', 'melee', 'ranged'):
            game_world.clear()
            arena, player, camera = scene()
            player.combat.hp = 10000
            waves = WaveManager(player, player.targets, player.projectiles)
            waves.load(3, selection)
            for _ in range(15 * 120):
                game_framework.frame_time = 1 / 120
                waves.update()
                player.update()
                for enemy in player.targets:
                    enemy.update()
                self.assert_separate(player.targets)
            self.assertEqual(len(player.targets), 16)


class SpacingRenderTests(unittest.TestCase):
    def test_spawned_enemies_are_visually_separate(self):
        pico2d.open_canvas(1280, 720)
        try:
            play_mode.init()
            play_mode.waves.load(3, 'all')
            play_mode.player.x, play_mode.player.y = 0, 25
            play_mode.camera.follow(play_mode.player)
            game_framework.frame_time = 1
            play_mode.update()
            play_mode.render()
            capture_png(ROOT / 'shots/enemy-spacing.png', 1280, 720)
            for index, enemy in enumerate(play_mode.enemies):
                for other in play_mode.enemies[index + 1:]:
                    self.assertFalse(overlaps(enemy, enemy.x, enemy.y, other))
        finally:
            play_mode.finish()
            pico2d.close_canvas()


if __name__ == '__main__':
    unittest.main()
