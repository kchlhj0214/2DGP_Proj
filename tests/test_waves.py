"""웨이브 교체, 동시 출현, 원거리 발사와 탄환의 실제 전투 판정 검사."""

import copy
import json
from math import pi
import unittest
from unittest.mock import patch

from test_scale import ROOT, capture_png, scene
import pico2d
import game_framework
import game_world
import play_mode
from enemy import MeleeEnemy
from projectile import Projectile
from ranged_enemy import RangedEnemy
from combat_data import ENEMIES
from wave_data import RANGED
from wave_manager import WaveManager
from tools.generate_data import validate_waves


def controller():
    game_world.clear()
    arena, player, camera = scene()
    enemies, projectiles = [], []
    player.targets, player.projectiles = enemies, projectiles
    manager = WaveManager(player, enemies, projectiles)
    return player, manager


def elapse(manager, duration):
    game_framework.frame_time = duration
    manager.update()


def move_bullet(player, bullet, duration):
    remaining = duration
    while remaining > 1e-10:
        game_framework.frame_time = min(1 / 240, remaining)
        player.update()
        bullet.update()
        remaining -= game_framework.frame_time


class WaveTests(unittest.TestCase):
    def tearDown(self):
        game_world.clear()

    def test_four_simultaneous_gates_every_point_three_seconds(self):
        player, waves = controller()
        waves.load()
        self.assertEqual((len(waves.enemies), waves.pending), (4, 8))
        self.assertEqual({gate for _, gate, _ in waves.spawn_log}, {'north', 'south', 'west', 'east'})
        for enemy in waves.enemies:
            self.assertTrue(player.arena.contains_box(enemy.x, enemy.y - .45, .9, .9))
        elapse(waves, .299)
        self.assertEqual(len(waves.enemies), 4)
        elapse(waves, .001)
        self.assertEqual((len(waves.enemies), waves.pending), (8, 4))
        elapse(waves, .3)
        self.assertEqual((len(waves.enemies), waves.pending), (12, 0))
        self.assertEqual(sum(isinstance(e, RangedEnemy) for e in waves.enemies), 4)
        for gate in ('north', 'south', 'west', 'east'):
            self.assertEqual([t for t, g, _ in waves.spawn_log if g == gate], [0, .3, .6])

    def test_count_and_kinds_for_every_wave_and_mode(self):
        for number, count in ((1, 12), (2, 12), (3, 16), (4, 0)):
            for selection in ('all', 'melee', 'ranged'):
                player, waves = controller()
                waves.load(number, selection)
                elapse(waves, 1)
                self.assertEqual(len(waves.enemies), count)
                self.assertEqual(waves.pending, 0)
                ranged = sum(isinstance(e, RangedEnemy) for e in waves.enemies)
                self.assertEqual(ranged, 0 if selection == 'melee' else count if selection == 'ranged' else min(count, 4))

    def test_q_cycles_zero_one_melee_one_ranged_and_clears_old_wave(self):
        player, waves = controller()
        waves.load(3)
        old = waves.enemies[:]
        bullet = Projectile('old-single', 10, 0, 0, RANGED['ranged'], player)
        waves.add_projectile(bullet)
        player.combat.hp, player.combat.energy = 70, 20
        for expected, count in (('none', 0), ('melee', 1), ('ranged', 1), ('none', 0)):
            self.assertTrue(waves.handle_key(pico2d.SDLK_q))
            elapse(waves, 10)
            self.assertEqual((waves.single_mode, len(waves.enemies), waves.pending), (expected, count, 0))
            self.assertFalse(waves.projectiles)
            self.assertEqual((player.combat.hp, player.combat.energy), (70, 20))
            if count:
                self.assertEqual(isinstance(waves.enemies[0], RangedEnemy), expected == 'ranged')
            for layer in game_world.world:
                self.assertNotIn(bullet, layer)
                self.assertTrue(all(enemy not in layer for enemy in old))

    def test_number_keys_leave_single_mode_and_fourth_wave_allows_single_test(self):
        for code in (pico2d.SDLK_1, pico2d.SDLK_2, pico2d.SDLK_3, pico2d.SDLK_4,
                     pico2d.SDLK_8, pico2d.SDLK_9, pico2d.SDLK_0):
            player, waves = controller()
            waves.load(4)
            waves.handle_key(pico2d.SDLK_q)
            waves.handle_key(pico2d.SDLK_q)
            self.assertEqual((waves.single_mode, len(waves.enemies)), ('melee', 1))
            waves.handle_key(code)
            self.assertIsNone(waves.single_mode)
            elapse(waves, 1)
            expected = 0 if waves.number == 4 else 16 if waves.number == 3 else 12
            self.assertEqual(len(waves.enemies), expected)

    def test_jump_and_filter_remove_old_objects_and_queue_keep_player(self):
        player, waves = controller()
        waves.load()
        old = waves.enemies[:]
        old_ids = {enemy.identifier for enemy in old}
        bullet = Projectile('old', 10, 0, 0, RANGED['ranged'], player)
        waves.add_projectile(bullet)
        player.x, player.y = 4, 5
        player.combat.hp, player.combat.energy = 70, 20
        self.assertTrue(waves.handle_key(pico2d.SDLK_9))
        self.assertEqual(waves.selection, 'ranged')
        self.assertTrue(all(isinstance(e, RangedEnemy) for e in waves.enemies))
        self.assertFalse(old_ids.intersection(e.identifier for e in waves.enemies))
        self.assertFalse(waves.projectiles)
        for layer in game_world.world:
            self.assertNotIn(bullet, layer)
            self.assertTrue(all(e not in layer for e in old))
        self.assertEqual((player.x, player.y, player.combat.hp, player.combat.energy), (4, 5, 70, 20))
        self.assertTrue(waves.handle_key(pico2d.SDLK_3))
        self.assertEqual((waves.number, waves.selection, waves.pending), (3, 'ranged', 12))
        waves.handle_key(pico2d.SDLK_8)
        self.assertTrue(all(type(e) is MeleeEnemy for e in waves.enemies))
        waves.handle_key(pico2d.SDLK_0)
        elapse(waves, 1)
        self.assertEqual(sum(isinstance(e, RangedEnemy) for e in waves.enemies), 4)
        waves.handle_key(pico2d.SDLK_4)
        elapse(waves, 100)
        self.assertEqual((waves.number, len(waves.enemies), waves.pending), (4, 0, 0))
        self.assertFalse(waves.handle_key(pico2d.SDLK_7))

    def test_frame_rate_does_not_change_spawn_timeline(self):
        baseline = None
        for fps in (15, 30, 60, 144):
            player, waves = controller()
            waves.load(3)
            for _ in range(fps):
                elapse(waves, 1 / fps)
            if baseline is None:
                baseline = waves.spawn_log
            self.assertEqual(waves.spawn_log, baseline)
            self.assertEqual(len(waves.enemies), 16)

    def test_sheet_references_counts_and_cells(self):
        source = json.loads((ROOT / 'data/waves.json').read_text(encoding='utf-8'))
        scale = json.loads((ROOT / 'data/scale.json').read_text(encoding='utf-8'))
        combat = json.loads((ROOT / 'data/combat.json').read_text(encoding='utf-8'))
        for name, field, value in (('waves', 'melee_id', 'missing'), ('waves', 'ranged_id', 'missing'),
                                   ('waves', 'melee_per_gate', -1), ('waves', 'ranged_per_gate', 1.5),
                                   ('ranged', 'character_id', 'missing'), ('ranged', 'attack_interval_s', None),
                                   ('settings', 'spawn_interval_s', 0),
                                   ('single_modes', 'enemy_id', 'missing'),
                                   ('single_modes', 'count', 2)):
            data = copy.deepcopy(source)
            data[name][0][field] = value
            with self.assertRaises(ValueError):
                validate_waves(data, scale, combat)


class RangedTests(unittest.TestCase):
    def test_approach_stop_fire_immediately_then_three_seconds(self):
        player, waves = controller()
        ranged = RangedEnemy('ranged-test', RANGED['ranged'], 11, 0, player, waves.add_projectile)
        for _ in range(120):
            game_framework.frame_time = 1 / 240
            ranged.update()
        self.assertAlmostEqual(ranged.x, 10)
        self.assertEqual(ranged.shots, 1)
        self.assertEqual(ranged.state, 'shoot')
        # 마지막 발사 시각을 기준으로 정확히 3초를 확인한다.
        while ranged.cooldown > 1 / 240 + 1e-9:
            game_framework.frame_time = 1 / 240
            ranged.update()
        self.assertEqual(ranged.shots, 1)
        game_framework.frame_time = ranged.cooldown
        ranged.update()
        self.assertEqual(ranged.shots, 2)
        player.x = 9
        x = ranged.x
        game_framework.frame_time = .1
        ranged.update()
        self.assertEqual(ranged.x, x)  # 가까워져도 도주하지 않는다.

    def test_projectile_parry_charges_without_using_melee_stun(self):
        player, waves = controller()
        player.combat.right_down()
        bullet = Projectile('test', 2, 0, pi, RANGED['ranged'], player)
        move_bullet(player, bullet, .2)
        self.assertFalse(bullet.active)
        self.assertEqual(bullet.result, 'parry')
        self.assertEqual((player.combat.hp, player.combat.energy), (100, 10))
        self.assertFalse(player.combat.stunned_one)
        melee = MeleeEnemy('melee-test', ENEMIES['melee'], 1.6, 0, player)
        self.assertEqual(player.combat.receive('sword', melee, 10, 10), 'parry')
        self.assertEqual(melee.state, 'stunned')

    def test_block_rear_damage_and_boundary_removal(self):
        player, waves = controller()
        player.combat.right_down()
        game_framework.frame_time = 1
        player.update()
        bullet = Projectile('front', 2, 0, pi, RANGED['ranged'], player)
        move_bullet(player, bullet, .2)
        self.assertEqual((bullet.result, player.combat.hp, player.combat.energy), ('block', 100, 0))
        bullet = Projectile('rear', -2, 0, 0, RANGED['ranged'], player)
        move_bullet(player, bullet, .2)
        self.assertEqual((bullet.result, player.combat.hp), ('hit', 90))
        bullet = Projectile('outside', player.arena.radius - .05, 0, 0, RANGED['ranged'], player)
        move_bullet(player, bullet, .02)
        self.assertEqual(bullet.result, 'boundary')

    def test_beam_erases_projectiles_between_damage_ticks(self):
        player, waves = controller()
        player.combat.energy = 10
        player.combat.fire()
        bullet = Projectile('across', 5, 3, -pi / 2, RANGED['ranged'], player)
        player.projectiles.append(bullet)
        move_bullet(player, bullet, .3)
        self.assertEqual(bullet.result, 'beam')
        self.assertEqual(player.combat.beam.ticks, 1)
        self.assertLess(player.combat.beam.age, .5)


class DebugInputRenderTests(unittest.TestCase):
    def test_debug_keys_through_game_mode_and_real_render(self):
        pico2d.open_canvas(1280, 720)
        try:
            play_mode.init()

            def press(code):
                event = pico2d.Event(pico2d.SDL_KEYDOWN)
                event.key = code
                with patch.object(pico2d, 'get_events', return_value=[event]), \
                     patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                    play_mode.handle_events()

            press(pico2d.SDLK_3)
            press(pico2d.SDLK_9)
            game_framework.frame_time = 1
            play_mode.update()
            self.assertEqual((play_mode.waves.number, len(play_mode.enemies)), (3, 16))
            self.assertTrue(all(isinstance(e, RangedEnemy) for e in play_mode.enemies))
            # 카메라 중심 유지 상태로 북쪽 입구 출현을 캡처한다.
            play_mode.player.x, play_mode.player.y = 0, 25
            play_mode.camera.follow(play_mode.player)
            play_mode.render()
            capture_png(ROOT / 'shots/wave-ranged.png', 1280, 720)
            press(pico2d.SDLK_ESCAPE)
            self.assertTrue(play_mode.paused)
            before = play_mode.waves.elapsed
            game_framework.frame_time = 1
            play_mode.update()
            self.assertEqual(play_mode.waves.elapsed, before)
            press(pico2d.SDLK_8)
            self.assertTrue(play_mode.paused)
            self.assertEqual((play_mode.waves.selection, len(play_mode.enemies), play_mode.waves.pending), ('melee', 4, 12))
            press(pico2d.SDLK_ESCAPE)
            press(pico2d.SDLK_0)
            game_framework.frame_time = 1
            play_mode.update()
            play_mode.render()
            capture_png(ROOT / 'shots/wave-mixed.png', 1280, 720)
            press(pico2d.SDLK_4)
            self.assertFalse(play_mode.enemies)
            self.assertFalse(play_mode.projectiles)
            self.assertEqual(play_mode.waves.pending, 0)
            play_mode.render()
            capture_png(ROOT / 'shots/wave-four-wait.png', 1280, 720)
            press(pico2d.SDLK_r)
            self.assertEqual((play_mode.waves.number, play_mode.waves.selection), (1, 'all'))
            press(pico2d.SDLK_ESCAPE)
            press(pico2d.SDLK_q)
            self.assertEqual((play_mode.waves.single_mode, len(play_mode.enemies)), ('none', 0))
            self.assertTrue(play_mode.paused)
            press(pico2d.SDLK_q)
            self.assertEqual((play_mode.waves.single_mode, len(play_mode.enemies)), ('melee', 1))
            press(pico2d.SDLK_q)
            self.assertEqual((play_mode.waves.single_mode, len(play_mode.enemies)), ('ranged', 1))
            play_mode.player.y = 25
            play_mode.camera.follow(play_mode.player)
            play_mode.render()
            capture_png(ROOT / 'shots/single-enemy-debug.png', 1280, 720)
        finally:
            play_mode.finish()
            pico2d.close_canvas()


if __name__ == '__main__':
    unittest.main()
