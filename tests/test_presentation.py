"""Stand-alone checks for damage feedback and the real parry displacement."""

from math import dist, hypot, pi
from unittest import TestCase
from unittest.mock import Mock

from test_combat import actor, advance
from test_scale import pico2d

import game_framework
import play_mode
from combat_data import ENEMIES
from enemy import MeleeEnemy
from impact_effects import ImpactEffects
from presentation_data import VISUALS
from projectile import Projectile
from ranged_enemy import RangedEnemy
from sprites import clip_duration
from wave_data import RANGED


class PresentationTests(TestCase):
    def test_parry_snaps_up_and_recovers_without_changing_input_lock(self):
        player, enemy = actor()
        combat = player.combat
        combat.right_down()
        self.assertEqual(combat.parry_frame(), 0)
        combat.advance(.11)
        self.assertEqual(combat.parry_frame(), 8)
        combat.advance(.11)
        self.assertEqual(combat.receive('parry', enemy, 10, 10), 'parry')
        self.assertEqual(combat.parry_frame(), 8)
        combat.advance(.24)
        self.assertEqual(combat.parry_frame(), 15)
        self.assertEqual(combat.state, 'raising')
        combat.advance(.54)
        self.assertEqual(combat.state, 'guard')

    def test_defeated_enemies_render_unique_deaths_until_finished(self):
        player, melee = actor()
        ranged = RangedEnemy('ranged', RANGED['ranged'], 4, 0, player, Mock())
        player.sprites = Mock()
        elapsed = game_framework.frame_time
        try:
            for enemy, motion in ((melee, 'collapse'), (ranged, 'ash')):
                with self.subTest(motion=motion):
                    start = enemy.x, enemy.y
                    player.sprites.draw.reset_mock()
                    enemy.take_damage(enemy.hp)
                    self.assertEqual(enemy.state, 'dead')
                    enemy.draw()
                    self.assertEqual(player.sprites.draw.call_args.args[:2],
                                     (enemy.sprite_actor, motion))
                    self.assertEqual(player.sprites.draw.call_args.args[-1], 0.0)
                    duration = clip_duration(enemy.sprite_actor, motion)
                    game_framework.frame_time = duration / 2
                    enemy.update()
                    enemy.draw()
                    self.assertEqual(player.sprites.draw.call_args.args[-1], duration / 2)
                    enemy.update()
                    enemy.draw()
                    self.assertEqual(player.sprites.draw.call_count, 2)
                    self.assertEqual((enemy.x, enemy.y), start)
        finally:
            game_framework.frame_time = elapsed

    def test_parry_moves_collision_box_but_does_not_push_through_enemy(self):
        for blocked in (False, True):
            player, enemy = actor()
            if blocked:
                blocker = MeleeEnemy('wall', ENEMIES['melee'], enemy.x + enemy.width + .2, 0, player)
                player.targets.append(blocker)
            before = enemy.get_bb()
            advance(player, [enemy], .55)
            player.combat.right_down()
            advance(player, [enemy], .95)
            moved = enemy.get_bb()[0] - before[0]
            expected = .2 if blocked else enemy.height * VISUALS['parry']['push_height_ratio']
            self.assertAlmostEqual(moved, expected, places=5)
            self.assertEqual(enemy.state, 'stunned')
            self.assertEqual((player.x, player.y), (0, 0))

    def test_success_pushes_nearby_enemies_in_the_parry_cone_once(self):
        player, melee = actor(3, 3)
        ranged = RangedEnemy('ranged', RANGED['ranged'], 3, -3, player, Mock())
        outside = [MeleeEnemy(name, ENEMIES['melee'], x, y, player)
                   for name, x, y in (('rear', -3, 0), ('flank', 0, 5), ('distant', 7, 0))]
        dead = MeleeEnemy('dead', ENEMIES['melee'], 3, 0, player)
        dead.take_damage(dead.hp)
        player.targets.extend([ranged, *outside, dead])
        bullet = Projectile('shot', 1, 0, pi, RANGED['ranged'], player)
        player.combat.right_down()
        self.assertEqual(player.combat.receive('shot', bullet, 10, 10), 'parry')
        self.assertEqual((melee.recoil_age, ranged.recoil_age), (0, 0))
        self.assertEqual(ranged.pose(), ('stagger', 0))
        self.assertTrue(all(enemy.recoil_age is None for enemy in [*outside, dead]))
        advance(player, [melee, ranged], .12)
        self.assertGreater(hypot(melee.x, melee.y), hypot(3, 3))
        self.assertGreater(hypot(ranged.x, ranged.y), hypot(3, 3))
        self.assertEqual(ranged.shots, 0)
        self.assertEqual(ranged.pose()[0], 'stagger')
        self.assertGreater(ranged.pose()[1], 0)
        recoil = (melee.recoil_age, ranged.recoil_age)
        self.assertEqual(player.combat.receive('sword', melee, 10, 10), 'parry')
        self.assertEqual((melee.recoil_age, ranged.recoil_age), recoil)
        advance(player, [melee, ranged], VISUALS['parry']['push_s'])
        self.assertNotEqual(ranged.pose()[0], 'stagger')

    def test_three_equal_sound_triggers_and_stronger_max_shake(self):
        def fire(energy):
            player, enemy = actor()
            # The pulse starts once per damage tick, independent of the number of targets.
            player.targets.append(MeleeEnemy('second', ENEMIES['melee'], 3.0, 0, player))
            effects = player.effects = ImpactEffects(player.camera)
            effects.sound = Mock()
            player.combat.energy = energy
            self.assertTrue(player.combat.fire())
            self.assertEqual(effects.sound.play.call_count, 1)
            effects.update(.01)
            strength = hypot(player.camera.shake_x, player.camera.shake_y)
            advance(player, [], .49)
            self.assertEqual(effects.sound.play.call_count, 1)
            advance(player, [], .01)
            self.assertEqual(effects.sound.play.call_count, 2)
            advance(player, [], .50)
            self.assertEqual(effects.sound.play.call_count, 3)
            advance(player, [], .50)
            self.assertEqual(effects.sound.play.call_count, 3)
            self.assertEqual(enemy.hp, 60 - 3 * energy / 2)
            return strength

        self.assertGreater(fire(40), fire(10))

    def test_beam_has_obtuse_tip_and_full_width_after_the_taper(self):
        for step in range(8):
            player, _ = actor()
            player.combat.aim = step*pi/4
            player.combat.energy = 40
            player.combat.fire()
            beam = player.combat.beam
            tip, left, far_left, far_right, right = beam.polygon()
            self.assertEqual(tip, beam.origin())
            self.assertNotEqual(tip, (player.x,player.y))
            self.assertAlmostEqual(dist(left,right), 4.2)
            self.assertAlmostEqual(dist(far_left,far_right), 4.2)
            # A negative dot product proves the two flare edges form an obtuse angle.
            self.assertLess(sum((a-c)*(b-c) for a,b,c in zip(left,right,tip)), 0)

    def test_hp_loss_freezes_world_not_feedback_and_blocks_do_not_flash(self):
        pico2d.open_canvas(1280, 720)
        try:
            play_mode.init()
            player, enemy = play_mode.player, play_mode.enemies[0]
            effects = player.effects
            self.assertIsNotNone(effects.sound)
            player.combat.state = 'guard'
            player.combat.aim = 0
            enemy.x, enemy.y = 2, 0
            self.assertEqual(player.combat.receive('blocked', enemy, 10, 10), 'block')
            self.assertFalse(effects.numbers)
            enemy.x = -2
            self.assertEqual(player.combat.receive('actual', enemy, 10, 10), 'hit')
            self.assertEqual(effects.numbers[0].amount, 10)
            self.assertTrue(effects.flashing(player))
            previous = player.combat.time
            game_framework.frame_time = effects.config['hitstop_s'] / 2
            play_mode.update()
            self.assertEqual(player.combat.time, previous)
            self.assertGreater(effects.time, 0)
            game_framework.frame_time = effects.config['flash_s']
            play_mode.update()
            self.assertGreater(player.combat.time, previous)
            self.assertFalse(effects.flashing(player))
        finally:
            play_mode.finish()
            pico2d.close_canvas()
