"""실제 입력 전달과 회전 칼 충돌을 포함한 도형 전투 회귀 검사."""

import copy
import json
from math import cos, pi, sin
import unittest
from unittest.mock import patch

from test_scale import ROOT, capture_png, key, scene
from tools.generate_data import validate_combat
import pico2d
import game_framework
import play_mode
from combat_data import ENEMIES, SYSTEMS
from enemy import MeleeEnemy
from geometry import box_points, intersects, oriented_box


def actor(x=None, y=0, identifier='one'):
    arena, player, camera = scene()
    spec = ENEMIES['melee']
    enemy = MeleeEnemy(identifier, spec, spec['stop_m'] if x is None else x, y, player)
    player.targets = [enemy]
    return player, enemy


def advance(player, enemies, duration, dt=1 / 240):
    remaining = duration
    while remaining > 1e-10:
        game_framework.frame_time = min(remaining, dt)
        player.update()
        for enemy in enemies:
            enemy.update()
        remaining -= game_framework.frame_time


class CombatTests(unittest.TestCase):
    def test_four_real_parries_then_beam_clear(self):
        player, enemy = actor()
        combat = player.combat
        for target_energy in (10, 20, 30, 40):
            deadline = combat.time + 6
            while combat.energy < target_energy and combat.time < deadline:
                if enemy.state == 'windup' and enemy.age >= .58 and combat.state == 'free':
                    combat.right_down()
                advance(player, [enemy], 1 / 240)
            self.assertEqual(combat.energy, target_energy)
            self.assertEqual(combat.hp, 100)
            combat.right_up()
            while combat.state == 'raising':
                advance(player, [enemy], 1 / 240)
        self.assertTrue(combat.fire())
        beam = combat.beam
        advance(player, [enemy], 1.5)
        self.assertEqual(enemy.hp, 0)
        self.assertEqual(beam.ticks, 3)
        self.assertEqual(combat.energy, 0)
        self.assertEqual(combat.state, 'free')

    def test_stage_thresholds_and_maximum(self):
        player, enemy = actor()
        combat = player.combat
        combat.right_down()
        for count in range(1, 6):
            self.assertEqual(combat.receive(count, enemy, 10, 10), 'parry')
            self.assertEqual(combat.energy, min(count * 10, 40))
        for energy, name, window in ((0, 'stage1', .3), (9, 'stage1', .3),
                                    (10, 'stage2', .22), (20, 'stage3', .15),
                                    (30, 'stage4', .1), (40, 'stage4', .1)):
            combat.energy = energy
            self.assertEqual(combat.stage()['id'], name)
            self.assertEqual(combat.stage()['parry_window_s'], window)

    def test_input_lock_guard_release_and_no_queue(self):
        player, _ = actor()
        combat = player.combat
        key(player, pico2d.SDL_KEYDOWN, pico2d.SDLK_d)
        combat.right_down()
        advance(player, [], .99)
        self.assertEqual(player.x, 0)
        self.assertFalse(combat.fire())
        combat.right_down()
        advance(player, [], .01)
        self.assertEqual(combat.state, 'guard')
        x = player.x
        advance(player, [], 1)
        self.assertAlmostEqual(player.x - x, 7 / 3.6)
        combat.right_up()
        self.assertEqual(combat.state, 'free')
        combat.right_down()
        self.assertEqual(combat.state, 'raising')

    def test_release_during_raise_does_not_cancel_lock(self):
        player, _ = actor()
        player.combat.right_down()
        player.combat.right_up()
        advance(player, [], .5)
        self.assertEqual(player.combat.state, 'raising')
        advance(player, [], .5)
        self.assertEqual(player.combat.state, 'free')
        self.assertEqual([kind for _, kind in player.combat.events], ['miss'])

    def test_front_90_degree_boundary_and_rear(self):
        for angle, result in ((-45, 'parry'), (45, 'parry'), (46, 'hit'), (180, 'hit')):
            player, enemy = actor(1.6 * cos(angle * pi / 180), 1.6 * sin(angle * pi / 180))
            player.combat.right_down()
            self.assertEqual(player.combat.receive(1, enemy, 10, 10), result)

    def test_guard_does_not_charge_and_rear_hurts(self):
        player, enemy = actor()
        combat = player.combat
        combat.right_down()
        advance(player, [], 1)
        self.assertEqual(combat.receive(1, enemy, 10, 10), 'block')
        self.assertEqual((combat.hp, combat.energy), (100, 0))
        enemy.x = -1.6
        self.assertEqual(combat.receive(2, enemy, 10, 10), 'hit')
        self.assertEqual(combat.hp, 90)

    def test_multi_parry_one_stun_and_no_invulnerability_extension(self):
        player, enemy = actor()
        other = MeleeEnemy('other', ENEMIES['melee'], 1.6, .2, player)
        combat = player.combat
        combat.right_down()
        self.assertEqual(combat.receive(1, enemy, 10, 10), 'parry')
        until = combat.success_invuln_until
        advance(player, [], .05)
        self.assertEqual(combat.receive(2, other, 10, 10), 'parry')
        self.assertEqual(combat.receive(2, other, 10, 10), 'ignored')
        self.assertEqual(combat.energy, 20)
        self.assertEqual(enemy.state, 'stunned')
        self.assertNotEqual(other.state, 'stunned')
        self.assertEqual(combat.success_invuln_until, until)
        advance(player, [], .3)
        self.assertEqual(combat.receive(3, other, 10, 10), 'invulnerable')
        self.assertEqual(combat.energy, 20)
        advance(player, [], .65)
        other.x = -1.6
        self.assertEqual(combat.receive(4, other, 10, 10), 'hit')

    def test_snapshot_window_and_hit_protection(self):
        player, enemy = actor()
        combat = player.combat
        combat.right_down()
        combat.receive(1, enemy, 10, 10)
        self.assertEqual(combat.window, .3)
        advance(player, [], .25)
        self.assertEqual(combat.receive(2, enemy, 10, 10), 'parry')
        combat.right_up()
        advance(player, [], .8)
        combat.right_down()
        self.assertEqual(combat.window, .15)
        advance(player, [], .16)
        self.assertEqual(combat.receive(3, enemy, 10, 10), 'hit')
        self.assertEqual(combat.receive(4, enemy, 10, 10), 'invulnerable')
        self.assertEqual(combat.energy, 20)

    def test_sword_collision_parry_and_stun_duration(self):
        player, enemy = actor()
        # .6초 예고 뒤 실제 칼이 몸체에 닿는 시점에 우클릭을 맞춘다.
        advance(player, [enemy], .55)
        self.assertEqual(enemy.state, 'windup')
        player.combat.right_down()
        advance(player, [enemy], .25)
        self.assertEqual((player.combat.hp, player.combat.energy), (100, 10))
        self.assertEqual(enemy.state, 'stunned')
        advance(player, [enemy], 1.2)
        self.assertEqual(enemy.state, 'stunned')
        advance(player, [enemy], .3)
        self.assertNotEqual(enemy.state, 'stunned')

    def test_sword_hits_once_and_fixed_telegraph_direction(self):
        player, enemy = actor()
        advance(player, [enemy], .8)
        self.assertEqual(player.combat.hp, 90)
        advance(player, [enemy], .1)
        self.assertEqual(player.combat.hp, 90)
        player, enemy = actor()
        advance(player, [enemy], .1)
        angle = enemy.angle
        player.y = 10
        advance(player, [enemy], .7)
        self.assertEqual(enemy.angle, angle)
        self.assertEqual(player.combat.hp, 100)

    def test_beam_zero_energy_and_timing_width_damage(self):
        player, enemy = actor(5, 0)
        self.assertFalse(player.combat.fire())
        player.combat.energy = 40
        self.assertTrue(player.combat.fire())
        beam = player.combat.beam
        self.assertEqual((beam.ticks, enemy.hp, beam.width), (1, 40, 3.6))
        self.assertEqual(player.combat.energy, 0)
        advance(player, [], .5)
        self.assertEqual((beam.ticks, enemy.hp), (2, 20))
        advance(player, [], .5)
        self.assertEqual((beam.ticks, enemy.hp), (3, 0))
        self.assertTrue(beam.active)
        advance(player, [], .5)
        self.assertFalse(beam.active)
        self.assertEqual(player.combat.state, 'free')

    def test_beam_origin_follows_but_direction_stays_and_no_queued_guard(self):
        player, enemy = actor(6, -3.1)
        other = MeleeEnemy('other', ENEMIES['melee'], 11, -3.1, player)
        player.targets.append(other)
        player.combat.energy = 10
        player.combat.fire()
        beam = player.combat.beam
        self.assertEqual((enemy.hp, other.hp), (55, 55))
        self.assertEqual(beam.width, 1.8)
        player.combat.aim = pi / 2
        key(player, pico2d.SDL_KEYDOWN, pico2d.SDLK_w)
        player.combat.right_down()
        self.assertFalse(player.combat.fire())
        advance(player, [], .5)
        self.assertEqual(beam.angle, 0)
        self.assertAlmostEqual(player.y, 14 / 3.6 * .5)
        self.assertEqual((enemy.hp, other.hp), (55, 55))
        advance(player, [], 1)
        self.assertEqual(player.combat.state, 'free')
        player.combat.right_down()
        self.assertEqual(player.combat.state, 'free')
        player.combat.right_up()
        player.combat.right_down()
        self.assertEqual(player.combat.state, 'raising')

    def test_death_interrupts_beam_without_free_cancel_on_hit(self):
        player, enemy = actor()
        player.combat.energy = 10
        player.combat.fire()
        player.combat.receive(1, enemy, 10, 10)
        self.assertEqual(player.combat.state, 'beam')
        advance(player, [], .51)
        player.combat.receive(2, enemy, 100, 10)
        self.assertEqual(player.combat.state, 'dead')
        self.assertIsNone(player.combat.beam)
        self.assertFalse(player.combat.fire())

    def test_sword_outcomes_match_across_frame_rates(self):
        for fps in (15, 30, 60, 144):
            player, enemy = actor()
            for _ in range(fps * 3):
                advance(player, [enemy], 1 / fps)
            self.assertEqual(player.combat.hp, 80)

    def test_data_validation_references_and_invariants(self):
        source = json.loads((ROOT / 'data/combat.json').read_text(encoding='utf-8'))
        scale = json.loads((ROOT / 'data/scale.json').read_text(encoding='utf-8'))
        for sheet, field, value in (('enemies', 'character_id', 'missing'),
                                    ('systems', 'energy_max', None),
                                    ('enemies', 'speed_kmph', 20),
                                    ('stages', 'parry_window_s', 2)):
            data = copy.deepcopy(source)
            data[sheet][0][field] = value
            with self.assertRaises(ValueError):
                validate_combat(data, scale)


class CombatRenderTests(unittest.TestCase):
    def test_playable_input_pause_restart_and_rendered_states(self):
        pico2d.open_canvas(1280, 720)
        try:
            play_mode.init()
            player = play_mode.player
            enemy = play_mode.enemies[0]
            enemy.x, enemy.y = enemy.data['stop_m'], 0
            for other in play_mode.enemies[1:]:
                other.take_damage(60)
            advance(player, [enemy], .55)
            event = pico2d.Event(pico2d.SDL_MOUSEBUTTONDOWN)
            event.button = pico2d.SDL_BUTTON_RIGHT
            with patch.object(pico2d, 'get_events', return_value=[event]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                play_mode.handle_events()
            play_mode.render()
            capture_png(ROOT / 'shots/combat-parry-window.png', 1280, 720)
            game_framework.frame_time = .25
            play_mode.update()
            self.assertEqual(player.combat.energy, 10)
            self.assertEqual(enemy.state, 'stunned')
            play_mode.render()
            capture_png(ROOT / 'shots/combat-parry-success.png', 1280, 720)
            event = pico2d.Event(pico2d.SDL_KEYDOWN)
            event.key = pico2d.SDLK_ESCAPE
            with patch.object(pico2d, 'get_events', return_value=[event]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                play_mode.handle_events()
            clock = player.combat.time
            game_framework.frame_time = 2
            play_mode.update()
            self.assertEqual(player.combat.time, clock)
            self.assertTrue(play_mode.paused)
            play_mode.paused = False
            advance(player, [], 1)
            player.combat.right_down()
            advance(player, [], 1)
            self.assertEqual(player.combat.state, 'guard')
            play_mode.render()
            capture_png(ROOT / 'shots/combat-guard.png', 1280, 720)
            player.combat.right_up()
            player.combat.energy = 40
            enemy.x, enemy.y = 5, 0
            event = pico2d.Event(pico2d.SDL_MOUSEBUTTONDOWN)
            event.button = pico2d.SDL_BUTTON_LEFT
            with patch.object(pico2d, 'get_events', return_value=[event]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                play_mode.handle_events()
            self.assertEqual(player.combat.state, 'beam')
            play_mode.render()
            capture_png(ROOT / 'shots/combat-beam.png', 1280, 720)
            event = pico2d.Event(pico2d.SDL_KEYDOWN)
            event.key = pico2d.SDLK_r
            with patch.object(pico2d, 'get_events', return_value=[event]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                play_mode.handle_events()
            self.assertIsNot(player, play_mode.player)
            self.assertEqual((play_mode.player.combat.hp, play_mode.player.combat.energy), (100, 0))
            self.assertTrue(all(e.hp == 60 for e in play_mode.enemies))
            # 실제로 회전하는 칼의 판정을 그린다.
            enemy = play_mode.enemies[0]
            enemy.x, enemy.y = enemy.data['stop_m'], 0
            advance(play_mode.player, [enemy], .68)
            self.assertEqual(enemy.state, 'swing')
            play_mode.render()
            capture_png(ROOT / 'shots/combat-sword.png', 1280, 720)
        finally:
            play_mode.finish()
            pico2d.close_canvas()


if __name__ == '__main__':
    unittest.main()
