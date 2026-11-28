import unittest
from unittest.mock import patch

from test_scale import read_canvas

import pico2d

import game_audio
import game_framework
import play_mode
from main_menu import MAIN_MENU


class MenuTests(unittest.TestCase):
    def setUp(self):
        pico2d.open_canvas(640, 360)
        game_audio.set_volume(100)
        game_framework.change_mode(MAIN_MENU)

    def tearDown(self):
        while game_framework.stack:
            game_framework.stack.pop().finish()
        game_audio.set_volume(100)
        pico2d.close_canvas()

    def event(self, event):
        with patch.object(pico2d, 'get_events', return_value=[event]), \
             patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
            game_framework.stack[-1].handle_events()

    def press(self, key):
        event = pico2d.Event(pico2d.SDL_KEYDOWN)
        event.key = key
        self.event(event)

    def mouse(self, x, y, kind=pico2d.SDL_MOUSEBUTTONDOWN):
        event = pico2d.Event(kind)
        event.x, event.y = x, 359 - y
        event.button = pico2d.SDL_BUTTON_LEFT
        self.event(event)

    def test_lobby_achievement_and_sound_pages_have_mouse_and_keyboard_navigation(self):
        MAIN_MENU.render()
        home = read_canvas(640, 360)
        self.mouse(85, 138)
        self.assertEqual(MAIN_MENU.active_page, 'achievements')
        MAIN_MENU.render()
        self.assertNotEqual(read_canvas(640, 360), home)
        self.press(pico2d.SDLK_ESCAPE)
        self.assertEqual(MAIN_MENU.active_page, 'home')
        self.press(pico2d.SDLK_DOWN)
        self.press(pico2d.SDLK_RETURN)
        self.assertEqual(MAIN_MENU.active_page, 'sound')
        self.mouse(320, 174)
        self.assertEqual(game_audio.volume, 50)
        self.mouse(80, 174, pico2d.SDL_MOUSEMOTION)
        self.assertEqual(game_audio.volume, 0)
        self.mouse(80, 174, pico2d.SDL_MOUSEBUTTONUP)
        self.press(pico2d.SDLK_RIGHT)
        self.assertEqual(game_audio.volume, 5)
        self.assertEqual(pico2d.Mix_Volume(0, -1), 6)

    def test_pause_freezes_battle_and_menu_exit_requires_confirmation(self):
        self.press(pico2d.SDLK_RETURN)
        self.assertIs(game_framework.stack[-1], play_mode)
        player = play_mode.player
        waves = play_mode.waves
        self.press(pico2d.SDLK_d)
        game_framework.frame_time = .25
        play_mode.update()
        self.press(pico2d.SDLK_ESCAPE)
        self.assertTrue(play_mode.paused)
        self.assertEqual(player.pressed_keys, set())
        timers = (player.combat.time, waves.elapsed, player.effects.time)
        game_framework.frame_time = 2.5
        play_mode.update()
        self.assertEqual((player.combat.time, waves.elapsed, player.effects.time), timers)
        play_mode.render()

        self.mouse(249, 173)
        self.assertLess(game_audio.volume, 50)
        self.mouse(130, 173, pico2d.SDL_MOUSEBUTTONUP)
        self.mouse(270, 244)
        self.assertFalse(play_mode.paused)
        self.assertIs(play_mode.player, player)
        self.press(pico2d.SDLK_ESCAPE)

        self.mouse(270, 127)
        self.assertEqual(play_mode.pause_menu.confirm, 'menu')
        self.press(pico2d.SDLK_RETURN)  # The confirmation defaults to Cancel.
        self.assertTrue(play_mode.paused)
        self.assertIs(play_mode.player, player)

        self.mouse(270, 127)
        self.press(pico2d.SDLK_LEFT)
        self.press(pico2d.SDLK_RETURN)
        self.assertIs(game_framework.stack[-1], MAIN_MENU)
        self.assertIsNone(play_mode.player)
        self.assertLess(game_audio.volume, 50)

    def test_confirmed_restart_starts_a_fresh_battle_at_the_selected_volume(self):
        self.press(pico2d.SDLK_RETURN)
        player = play_mode.player
        player.combat.hp = 40
        game_audio.set_volume(35)
        self.press(pico2d.SDLK_ESCAPE)
        self.press(pico2d.SDLK_DOWN)
        self.press(pico2d.SDLK_RETURN)
        self.assertEqual(play_mode.pause_menu.confirm, 'restart')
        self.press(pico2d.SDLK_LEFT)
        self.press(pico2d.SDLK_RETURN)
        self.assertIsNot(play_mode.player, player)
        self.assertEqual(play_mode.player.combat.hp, 100)
        self.assertEqual(play_mode.waves.elapsed, 0)
        self.assertFalse(play_mode.paused)
        self.assertEqual(game_audio.volume, 35)
