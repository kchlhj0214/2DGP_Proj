"""웨이브 교체, 순차 입장, 원거리 발사와 탄환의 실제 전투 판정 검사."""

import copy
import json
from math import cos, pi, radians, sin
import unittest
from unittest.mock import patch

from test_scale import ROOT, capture_png, read_canvas, scene
import pico2d
import game_framework
import game_world
import play_mode
from enemy import MeleeEnemy
from projectile import Projectile
from ranged_enemy import RangedEnemy
from combat_data import ENEMIES
from presentation_data import VISUALS
from wave_data import GATES, RANGED, SETTINGS
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

    def test_iron_gates_open_before_a_feet_first_bridge_crossing(self):
        player, waves = controller()
        waves.load()
        self.assertEqual((len(waves.enemies), waves.pending), (0, 8))
        self.assertTrue(all(waves.gate_opening(gate) == 0 for gate in GATES))
        first, second_row = waves.queue[0], waves.queue[4]
        self.assertEqual(first.gate['id'], second_row.gate['id'])
        self.assertGreater(second_row.enemy.y - first.enemy.y, first.enemy.height)
        self.assertNotIn(first.enemy, game_world.world[1])
        elapse(waves, .8)
        self.assertGreater(waves.gate_opening('north'), waves.gate_opening('east'))
        self.assertTrue(all(entry.visible == 0 for entry in waves.queue))
        elapse(waves, .32)
        self.assertEqual(waves.gate_opening('north'), 1)
        self.assertTrue(0 < first.visible < 1)
        self.assertEqual(second_row.visible, 0)
        self.assertLess(first.enemy.y - first.enemy.height / 2, waves.portal_distance)
        self.assertFalse(waves.enemies)
        elapse(waves, first.arrival_at - waves.elapsed)
        self.assertEqual(waves.enemies, [first.enemy])
        self.assertEqual(first.visible, 1)
        elapse(waves, 4)
        for enemy in waves.enemies:
            foot_height = player.boundary_height
            foot_y = enemy.y - (enemy.height - foot_height) / 2
            self.assertTrue(player.arena.contains_box(enemy.x, foot_y, enemy.width, foot_height))
        self.assertEqual((len(waves.enemies), waves.pending), (8, 0))
        self.assertEqual(sum(isinstance(e, RangedEnemy) for e in waves.enemies), 4)
        self.assertEqual([gate for _, gate, _ in waves.spawn_log], list(GATES) * 2)
        gap = SETTINGS['main']['arrival_interval_s']
        for first_arrival, second_arrival in zip(waves.spawn_log, waves.spawn_log[1:]):
            self.assertAlmostEqual(second_arrival[0] - first_arrival[0], gap)

    def test_count_and_kinds_for_every_wave_and_mode(self):
        for number, count in ((1, 8), (2, 12), (3, 16), (4, 0)):
            for selection in ('all', 'melee', 'ranged'):
                player, waves = controller()
                waves.load(number, selection)
                elapse(waves, 8)
                self.assertEqual(len(waves.enemies), count)
                self.assertEqual(waves.pending, 0)
                ranged = sum(isinstance(e, RangedEnemy) for e in waves.enemies)
                self.assertEqual(ranged, 0 if selection == 'melee' else count if selection == 'ranged' else min(count, 4))
                if number == 1 and selection == 'all':
                    for gate in ('north', 'south', 'east', 'west'):
                        self.assertEqual([kind for _, entry, kind in waves.spawn_log if entry == gate],
                                         ['melee', 'ranged'])

    def test_only_a_complete_clear_advances_and_resets_each_wave_timer(self):
        player, waves = controller()
        player.combat.hp, player.combat.energy = 70, 20
        waves.load(1, 'melee')
        self.assertEqual(waves.remaining_s, 120)
        elapse(waves, 3.1)
        waves.enemies[0].take_damage(waves.enemies[0].hp)
        waves.resolve_step()
        self.assertEqual((waves.number, waves.pending), (1, 7))
        self.assertAlmostEqual(waves.remaining_s, 116.9)
        for current, pending in ((1, 12), (2, 16), (3, 0)):
            elapse(waves, 7)
            for enemy in waves.enemies[:-1]:
                enemy.take_damage(enemy.hp)
            waves.resolve_step()
            self.assertEqual(waves.number, current)
            enemy = waves.enemies[-1]
            enemy.take_damage(enemy.hp)
            waves.resolve_step()
            self.assertEqual((waves.number, waves.pending, waves.selection), (current + 1, pending, 'melee'))
            self.assertEqual(waves.remaining_s, None if current == 3 else 120)
        self.assertEqual((player.combat.hp, player.combat.energy), (70, 20))

    def test_q_cycles_zero_one_melee_one_ranged_and_clears_old_wave(self):
        player, waves = controller()
        waves.load(3)
        old = [entry.enemy for entry in waves.queue]
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
            elapse(waves, 8)
            expected = {1: 8, 2: 12, 3: 16, 4: 0}[waves.number]
            self.assertEqual(len(waves.enemies), expected)

    def test_jump_and_filter_remove_old_objects_and_queue_keep_player(self):
        player, waves = controller()
        waves.load()
        elapse(waves, 3.5)
        old = waves.enemies[:]
        old_ids = {enemy.identifier for enemy in old} | {entry.enemy.identifier for entry in waves.queue}
        bullet = Projectile('old', 10, 0, 0, RANGED['ranged'], player)
        waves.add_projectile(bullet)
        player.x, player.y = 4, 5
        player.combat.hp, player.combat.energy = 70, 20
        self.assertTrue(waves.handle_key(pico2d.SDLK_9))
        self.assertEqual(waves.selection, 'ranged')
        self.assertTrue(all(isinstance(entry.enemy, RangedEnemy) for entry in waves.queue))
        self.assertFalse(old_ids.intersection(entry.enemy.identifier for entry in waves.queue))
        self.assertFalse(waves.projectiles)
        for layer in game_world.world:
            self.assertNotIn(bullet, layer)
            self.assertTrue(all(e not in layer for e in old))
        self.assertEqual((player.x, player.y, player.combat.hp, player.combat.energy), (4, 5, 70, 20))
        self.assertTrue(waves.handle_key(pico2d.SDLK_3))
        self.assertEqual((waves.number, waves.selection, waves.pending), (3, 'ranged', 16))
        waves.handle_key(pico2d.SDLK_8)
        self.assertTrue(all(type(entry.enemy) is MeleeEnemy for entry in waves.queue))
        waves.handle_key(pico2d.SDLK_0)
        elapse(waves, 8)
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
            for _ in range(fps * 8):
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
                                   ('settings', 'arrival_interval_s', 0),
                                   ('settings', 'time_limit_s', 0),
                                   ('settings', 'entrance_speed_mps', .1),
                                   ('settings', 'reveal_m', 8),
                                   ('single_modes', 'enemy_id', 'missing'),
                                   ('single_modes', 'count', 2)):
            data = copy.deepcopy(source)
            data[name][0][field] = value
            with self.assertRaises(ValueError):
                validate_waves(data, scale, combat)


class RangedTests(unittest.TestCase):
    def test_parry_intercepts_a_sword_and_bolt_beyond_the_body(self):
        player, waves = controller()
        player.combat.right_down()
        enemy = MeleeEnemy('long-swing', ENEMIES['melee'], 8.1, 0, player)
        enemy.angle = pi
        enemy.age = enemy.data['swing_s'] / 2
        enemy.attack_id = 'long-swing'
        enemy.resolve_sword()
        self.assertEqual(player.combat.energy, 0)

        enemy.x = 7.8
        enemy.resolve_sword()
        self.assertEqual(player.combat.energy, 10)
        self.assertEqual(enemy.state, 'stunned')

        bolt = Projectile('long-bolt', 5.6, 0, pi, RANGED['ranged'], player)
        move_bullet(player, bolt, .02)
        self.assertTrue(bolt.active)
        move_bullet(player, bolt, .03)
        self.assertEqual(bolt.result, 'parry')
        self.assertGreater(bolt.x - bolt.radius, player.get_bb()[2])
        self.assertEqual((player.combat.hp, player.combat.energy), (100, 20))

    def test_parry_boundaries_match_for_swords_and_bolts_under_camera_projection(self):
        pitch = VISUALS['arena']['floor_y_ratio']
        for floor_y_ratio, zoom in ((1.0, 1.0), (pitch, 1.0), (pitch, .417)):
            for heading in (0, 90, 180, 270):
                aim = radians(heading)
                for offset, expected in ((-46, 'hit'), (-45, 'parry'), (45, 'parry'), (46, 'hit')):
                    angle = aim + radians(offset)
                    dx, dy = cos(angle), sin(angle)
                    for attack in ('sword', 'bolt'):
                        with self.subTest(pitch=floor_y_ratio, zoom=zoom, heading=heading,
                                          offset=offset, attack=attack):
                            player, _ = controller()
                            camera = player.camera
                            camera.floor_y_ratio, camera.zoom = floor_y_ratio, zoom
                            x, y = camera.to_screen(12 * cos(aim), 12 * sin(aim))
                            event = pico2d.Event(pico2d.SDL_MOUSEMOTION)
                            event.x, event.y = round(x), round(camera.height_px - 1 - y)
                            player.handle_event(event)
                            player.combat.right_down()
                            if attack == 'sword':
                                enemy = MeleeEnemy(attack, ENEMIES['melee'], 2.9 * dx, 2.9 * dy, player)
                                enemy.angle = angle + pi
                                enemy.attack_id = attack
                                enemy.age = enemy.data['swing_s'] / 2
                                enemy.resolve_sword()
                                self.assertEqual(player.combat.events[-1][1], expected)
                            else:
                                bolt = Projectile(attack, 3.25 * dx, 3.25 * dy, angle + pi,
                                                  RANGED['ranged'], player)
                                move_bullet(player, bolt, .22)
                                self.assertEqual(bolt.result, expected)

    def test_approach_stop_fire_immediately_then_three_seconds(self):
        player, waves = controller()
        ranged = RangedEnemy('ranged-test', RANGED['ranged'], 16, 0, player, waves.add_projectile)
        game_framework.frame_time = .1
        ranged.update()
        self.assertEqual(ranged.shots, 0)
        for _ in range(120):
            game_framework.frame_time = 1 / 240
            ranged.update()
        self.assertAlmostEqual(ranged.x, 15)
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

    def test_walking_guard_blocks_side_projectile(self):
        player, _ = controller()
        player.combat.aim = -pi / 2
        player.combat.right_down()
        game_framework.frame_time = 1
        player.update()
        player.pressed_keys.add(pico2d.SDLK_d)
        bullet = Projectile('side', 3, 0, pi, RANGED['ranged'], player)
        move_bullet(player, bullet, .3)
        self.assertEqual((bullet.result, player.combat.hp, player.combat.energy), ('block', 100, 0))


class DebugInputRenderTests(unittest.TestCase):
    @staticmethod
    def sprite_pixels(draw):
        pico2d.clear_canvas()
        empty = read_canvas(640, 360)
        draw()
        frame = read_canvas(640, 360)
        return {divmod(i // 4, 640) for i in range(0, len(frame), 4)
                if empty[i:i + 4] != frame[i:i + 4]}

    def test_bridge_sprite_reveal_keeps_the_feet_anchored_in_the_renderer(self):
        pico2d.open_canvas(640, 360)
        try:
            play_mode.init()
            entry = play_mode.waves.queue[0]
            enemy = entry.enemy
            enemy.x, enemy.y = 0, 0

            def occupied_rows(reveal):
                pico2d.clear_canvas()
                empty = read_canvas(640, 360)
                entry.visible = reveal
                entry.draw(play_mode.waves.portal_distance)
                frame = read_canvas(640, 360)
                stride = 640 * 4
                return [y for y in range(360)
                        if empty[y * stride:(y + 1) * stride] != frame[y * stride:(y + 1) * stride]]

            self.assertEqual(occupied_rows(0), [])
            partial, full = occupied_rows(.35), occupied_rows(1)
            self.assertTrue(partial)
            self.assertEqual(max(partial), max(full))
            self.assertGreater(min(partial), min(full) + 10)
        finally:
            play_mode.finish()
            pico2d.close_canvas()

    def test_side_entries_are_clipped_at_the_doorway_in_both_directions(self):
        pico2d.open_canvas(640, 360)
        try:
            play_mode.init()
            waves = play_mode.waves
            player = play_mode.player
            camera = player.camera

            for entry in (e for e in waves.queue if e.gate['x_ratio']):
                with self.subTest(gate=entry.gate['id'], actor=entry.enemy.sprite_actor):
                    side = entry.gate['x_ratio']
                    edge = side * waves.portal_distance
                    camera.x = edge
                    enemy = entry.enemy

                    def draw_entry():
                        entry.draw(waves.portal_distance)

                    def draw_full_sprite():
                        player.sprites.draw(enemy.sprite_actor, 'walk', enemy, camera,
                                            enemy.angle, enemy.visual_time)

                    entry.advance(entry.passage_at + .01, waves.portal_distance, waves.choose_landing)
                    self.assertFalse(self.sprite_pixels(draw_entry))
                    entry.advance(entry.passage_at + .23, waves.portal_distance, waves.choose_landing)
                    partial = self.sprite_pixels(draw_entry)
                    full = self.sprite_pixels(draw_full_sprite)
                    self.assertTrue(0 < len(partial) < len(full))
                    screen_x, _ = camera.to_screen(edge, 0)
                    self.assertTrue(all(side * (x - screen_x) <= 1 for _, x in partial))
                    self.assertTrue(any(side * (x - screen_x) > 1 for _, x in full))
                    # The visible side includes upper-body pixels without lifting the whole image.
                    self.assertLess(min(y for y, _ in partial), 175)
                    entry.advance(entry.passage_at + .9, waves.portal_distance, waves.choose_landing)
                    self.assertEqual(self.sprite_pixels(draw_entry), self.sprite_pixels(draw_full_sprite))
        finally:
            play_mode.finish()
            pico2d.close_canvas()

    def test_south_entries_reveal_their_head_above_the_arch_before_their_feet(self):
        pico2d.open_canvas(640, 360)
        try:
            play_mode.init()
            waves = play_mode.waves
            player = play_mode.player
            camera = player.camera
            roof = player.arena.south_gate_roof(waves.portal_distance)
            camera.y = roof
            roof_row = camera.height_px / 2
            for entry in (e for e in waves.queue if e.gate['id'] == 'south'):
                with self.subTest(actor=entry.enemy.sprite_actor):
                    enemy = entry.enemy

                    def draw_entry():
                        entry.draw(waves.portal_distance)

                    def draw_full_sprite():
                        player.sprites.draw(enemy.sprite_actor, 'walk', enemy, camera,
                                            enemy.angle, enemy.visual_time)

                    entry.advance(entry.passage_at + .01, waves.portal_distance, waves.choose_landing)
                    self.assertFalse(self.sprite_pixels(draw_entry))
                    entry.advance(entry.passage_at + .36, waves.portal_distance, waves.choose_landing)
                    partial = self.sprite_pixels(draw_entry)
                    full = self.sprite_pixels(draw_full_sprite)
                    self.assertTrue(0 < len(partial) < len(full))
                    self.assertTrue(all(row <= roof_row for row, _ in partial))
                    self.assertAlmostEqual(min(row for row, _ in partial), min(row for row, _ in full), delta=1)
                    self.assertTrue(any(row > roof_row for row, _ in full))
                    entry.advance(entry.arrival_at - .02, waves.portal_distance, waves.choose_landing)
                    self.assertEqual(self.sprite_pixels(draw_entry), self.sprite_pixels(draw_full_sprite))
        finally:
            play_mode.finish()
            pico2d.close_canvas()

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
            game_framework.frame_time = 7
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
            self.assertEqual((play_mode.waves.selection, len(play_mode.enemies), play_mode.waves.pending), ('melee', 0, 16))
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

    def test_timeout_stops_the_clock_and_movement_until_restart(self):
        pico2d.open_canvas(640, 360)
        try:
            play_mode.init()
            wave = play_mode.waves
            player = play_mode.player
            wave.elapsed = 119.95
            player.pressed_keys.add(pico2d.SDLK_d)
            game_framework.frame_time = .04
            play_mode.update()
            self.assertFalse(wave.timed_out)
            self.assertGreater(wave.remaining_s, 0)
            game_framework.frame_time = .2
            play_mode.update()
            self.assertTrue(wave.timed_out)
            self.assertEqual((wave.number, wave.remaining_s, player.combat.hp), (1, 0, 100))
            self.assertAlmostEqual(player.x, .05 * player.speed_mps)
            stopped = (player.x, player.combat.time)
            self.assertFalse(player.pressed_keys)
            game_framework.frame_time = 2
            play_mode.update()
            self.assertEqual((player.x, player.combat.time), stopped)
            event = pico2d.Event(pico2d.SDL_KEYDOWN)
            event.key = pico2d.SDLK_r
            with patch.object(pico2d, 'get_events', return_value=[event]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                play_mode.handle_events()
            self.assertEqual((play_mode.waves.number, play_mode.waves.remaining_s), (1, 120))
            self.assertFalse(play_mode.waves.timed_out)
        finally:
            play_mode.finish()
            pico2d.close_canvas()


if __name__ == '__main__':
    unittest.main()
