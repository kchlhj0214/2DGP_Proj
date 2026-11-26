"""Boss attack geometry, defense choices and the final wave."""

from math import pi
from unittest import TestCase

from test_combat import advance
from test_scale import scene
from test_waves import controller, elapse
from orc_boss import BOSS, CHARGE, ROCK, SLAM, SWING, OrcBoss
from projectile import Projectile
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

    def test_charge_can_miss_get_parried_or_chip_a_guard(self):
        for method in ('dodge', 'hit', 'parry', 'guard'):
            with self.subTest(method=method):
                player, boss = encounter()
                boss.begin('charge')
                advance(player, [boss], CHARGE['windup_s'] - .035)
                if method == 'dodge':
                    player.y = CHARGE['width_m']
                defend(player, method)
                advance(player, [boss], 1.2)
                self.assertEqual(boss.state, 'recovery')
                self.assertEqual(boss.angle, 0)
                self.assertEqual(boss.staggered, method == 'parry')
                damage = {'hit': CHARGE['damage'], 'guard': CHARGE['damage'] / 4}.get(method, 0)
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

    def test_slam_guard_takes_chip_parry_cancels_all_falling_rocks(self):
        for method in ('guard', 'parry'):
            with self.subTest(method=method):
                player, boss = encounter()
                boss.begin('slam')
                advance(player, [boss], SLAM['windup_s'] - .04)
                defend(player, method)
                advance(player, [boss], .07)
                if method == 'parry':
                    self.assertEqual((boss.state, boss.rocks), ('recovery', []))
                    self.assertEqual((player.combat.hp, player.combat.energy), (100, 20))
                else:
                    self.assertEqual(boss.state, 'rocks')
                    self.assertEqual(len(boss.rocks), ROCK['count'])
                    self.assertEqual(player.combat.hp, 100 - SLAM['damage'] / 4)

    def test_each_falling_rock_has_its_own_guard_or_parry(self):
        for method in ('hit', 'guard', 'parry'):
            with self.subTest(method=method):
                player, boss = encounter(player_x=15)
                if method == 'guard':
                    defend(player, method)
                boss.begin('slam')
                advance(player, [boss], SLAM['windup_s'] + ROCK['flight_s'] - .05)
                first = boss.rocks[0]
                if method == 'parry':
                    defend(player, method)
                advance(player, [boss], .12)
                self.assertTrue(first.spent)
                damage = ROCK['damage'] if method == 'hit' else 0
                self.assertEqual(player.combat.hp, 100 - damage)
                self.assertEqual(player.combat.energy, 10 if method == 'parry' else 0)

    def test_sweep_parry_charges_and_guard_pushes_without_damage(self):
        for method in ('guard', 'parry', 'hit'):
            with self.subTest(method=method):
                player, boss = encounter()
                if method == 'guard':
                    defend(player, method)
                boss.begin('swing')
                advance(player, [boss], SWING['windup_s'] + .02)
                if method == 'parry':
                    defend(player, method)
                advance(player, [boss], SWING['swing_s'] + BOSS['push_s'])
                self.assertEqual(player.combat.hp, 100 - (SWING['damage'] if method == 'hit' else 0))
                self.assertEqual(player.combat.energy, 10 if method == 'parry' else 0)
                if method == 'guard':
                    self.assertAlmostEqual(player.x, 6 + player.arena.radius / 2)

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
