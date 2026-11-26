"""Boss attack geometry, defense choices and the final wave."""

from math import pi
from unittest import TestCase

from test_combat import advance
from test_scale import scene
from test_waves import controller, elapse
from orc_boss import BOSS, CHARGE, ROCK, SLAM, SWING, OrcBoss
from projectile import Projectile
from sprites import CLIPS
from wave_data import RANGED
import game_world


def encounter(player_x=6, player_y=0):
    _, player, _ = scene()
    player.x, player.y = player_x, player_y
    player.combat.aim = pi
    boss = OrcBoss('orc', player)
    player.targets = [boss]
    return player, boss


def defend(player, method):
    if method == 'guard':
        player.combat.right_down()
        advance(player, [], 1.01)
    elif method == 'parry':
        player.combat.right_down()


class BossTests(TestCase):
    def tearDown(self):
        game_world.clear()

    def test_render_plays_the_full_charge_stride_and_attack_follow_through(self):
        _, boss = encounter()
        boss.state = 'charge'
        for step in range(8):
            boss.visual_time = (step + .5) / 18
            self.assertEqual(boss.pose(), ('charge', 4 + step))
        self.assertEqual(CLIPS['boss', 'charge']['frames'], 12)
        for action, active in (('slam', 'rocks'), ('swing', 'swing')):
            with self.subTest(action=action):
                boss.pattern = action
                boss.state, boss.age = 'windup', 0
                self.assertEqual(boss.pose(), (action, 0))
                boss.state = active
                self.assertEqual(boss.pose(), (action, 4))
                boss.recover()
                self.assertEqual(boss.pose(), (action, 8))
                self.assertEqual(CLIPS['boss', action]['frames'], 12)

    def test_charge_can_miss_get_parried_or_chip_a_guard(self):
        for method in ('dodge', 'hit', 'parry', 'guard', 'rear-parry', 'rear-guard'):
            with self.subTest(method=method):
                player, boss = encounter()
                boss.begin('charge')
                advance(player, [boss], CHARGE['windup_s'] - .035)
                if method == 'dodge':
                    player.y = CHARGE['width_m']
                if method.startswith('rear-'):
                    player.combat.aim = 0
                defend(player, method.removeprefix('rear-'))
                advance(player, [boss], 1.2)
                self.assertEqual(boss.state, 'recovery')
                self.assertEqual(boss.angle, 0)
                self.assertEqual(boss.staggered, method == 'parry')
                damage = (CHARGE['damage'] if method in ('hit', 'rear-parry', 'rear-guard') else
                          CHARGE['damage'] / 4 if method == 'guard' else 0)
                self.assertEqual(player.combat.hp, 100 - damage)
                self.assertEqual(player.combat.energy, 20 if method == 'parry' else 0)
                if method == 'guard':
                    self.assertAlmostEqual(player.x, 6 + CHARGE['guard_push_m'])
                if method == 'parry':
                    self.assertLess(boss.x, 1)
                else:
                    self.assertAlmostEqual(boss.x, CHARGE['length_m'], places=3)
                pos = (boss.x, boss.y)
                advance(player, [boss], 2.97 - boss.age)
                self.assertEqual(boss.state, 'recovery')
                self.assertEqual((boss.x, boss.y), pos)
                advance(player, [boss], .04)
                self.assertEqual(boss.state, 'idle')

    def test_slam_ignores_guard_and_parry_but_leaves_room_to_dodge(self):
        for method in ('guard', 'parry', 'dodge'):
            with self.subTest(method=method):
                player, boss = encounter()
                boss.begin('slam')
                advance(player, [boss], SLAM['windup_s'] - .04)
                if method == 'dodge':
                    player.x = SLAM['radius_m'] + player.width
                self.assertIsNone(boss.eruption)
                defend(player, method)
                advance(player, [boss], .07)
                self.assertEqual(boss.state, 'rocks')
                self.assertEqual(len(boss.rocks), ROCK['count'])
                self.assertEqual(len(boss.eruption.spikes), SLAM['spikes'])
                self.assertEqual(player.combat.hp, 100 if method == 'dodge' else 100 - SLAM['damage'])
                self.assertEqual(player.combat.energy, 0)

    def test_each_falling_rock_has_its_own_guard_or_parry(self):
        for method in ('hit', 'guard', 'parry', 'outside'):
            with self.subTest(method=method):
                player, boss = encounter(player_x=15)
                if method == 'guard':
                    defend(player, method)
                boss.begin('slam')
                advance(player, [boss], SLAM['windup_s'] + ROCK['flight_s'] - .05)
                first = boss.rocks[0]
                player.x += ROCK['radius_m'] + (player.width if method == 'outside' else .25)
                player.combat.aim = pi if method == 'outside' else 0
                if method in ('parry', 'outside'):
                    defend(player, 'parry')
                advance(player, [boss], .12)
                self.assertTrue(first.spent)
                damage = ROCK['damage'] if method == 'hit' else 0
                self.assertEqual(player.combat.hp, 100 - damage)
                self.assertEqual(player.combat.energy, 10 if method == 'parry' else 0)

    def test_sweep_parry_charges_and_guard_pushes_without_damage(self):
        for aim, protected in ((pi, True), (pi / 2, True), (-pi / 2, False), (0, False)):
            for method in ('guard', 'parry'):
                with self.subTest(method=method, aim=aim):
                    player, boss = encounter()
                    player.combat.aim = aim
                    if method == 'guard':
                        defend(player, method)
                    boss.begin('swing')
                    advance(player, [boss], SWING['windup_s'] - .035)
                    if method == 'parry':
                        defend(player, method)
                    advance(player, [boss], SWING['swing_s'] + BOSS['push_s'] + .04)
                    self.assertEqual(player.combat.hp, 100 if protected else 100 - SWING['damage'])
                    self.assertEqual(player.combat.energy, 10 if protected and method == 'parry' else 0)
                    expected_x = 6 + player.arena.radius / 2 if protected and method == 'guard' else 6
                    self.assertAlmostEqual(player.x, expected_x)

    def test_boss_enters_wave_four_with_survivors_and_victory_stops_attacks(self):
        player, waves = controller()
        waves.load(3)
        elapse(waves, waves.remaining_s)
        survivors = list(waves.enemies)
        waves.resolve_step()
        self.assertTrue(waves.boss_pending)
        self.assertIsNone(waves.remaining_s)
        self.assertEqual(waves.enemies, survivors)
        elapse(waves, BOSS['arrival_s'] / 2)
        self.assertTrue(waves.boss_pending)
        elapse(waves, BOSS['arrival_s'] / 2)
        self.assertIsInstance(waves.boss, OrcBoss)
        self.assertEqual(waves.enemies, survivors + [waves.boss])
        bolt = Projectile('survivor-bolt', 10, 0, pi, RANGED['ranged'], player)
        waves.add_projectile(bolt)
        self.assertFalse(waves.won)
        waves.boss.take_damage(waves.boss.hp)
        waves.resolve_step()
        self.assertTrue(waves.won)
        self.assertEqual(waves.number, 4)
        self.assertEqual(waves.projectiles, [])
        self.assertNotIn(bolt, game_world.world[1])
