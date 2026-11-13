"""실제 pico2d를 사용하되 SDL dummy 드라이버로 화면과 입력을 사용하지 않는다."""

import copy
import ctypes
import json
from math import cos, hypot, pi, sin
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['SDL_RENDER_DRIVER'] = 'software'

from tools.generate_data import ROOT, generate, validate

generate()

import pico2d
import pico2d.pico2d as canvas
import game_framework
import game_world
import play_mode
from arena import Arena
from camera import Camera
from game_data import ARENAS, CHARACTERS, VIEWPORTS
from player import Player


def scene(width=1920, height=1080):
    camera = Camera(width, height, VIEWPORTS['main']['height_m'])
    arena = Arena(ARENAS['arena'], VIEWPORTS['main'], camera)
    player = Player(CHARACTERS['player'], VIEWPORTS['main'], arena, camera)
    return arena, player, camera


def key(player, event_type, code):
    event = pico2d.Event(event_type)
    event.key = code
    player.handle_event(event)


def capture_png(path, width, height):
    """실제로 그린 SDL 렌더 버퍼를 PNG로 저장한다. 합성 이미지가 아니다."""
    pixels = ctypes.create_string_buffer(width * height * 4)
    result = pico2d.SDL_RenderReadPixels(canvas.renderer, None,
                                        pico2d.SDL_PIXELFORMAT_RGBA32,
                                        pixels, width * 4)
    if result != 0:
        raise RuntimeError(pico2d.SDL_GetError())
    raw = pixels.raw
    rows = b''.join(b'\0' + raw[y * width * 4:(y + 1) * width * 4]
                    for y in range(height))

    def chunk(name, content):
        return (struct.pack('!I', len(content)) + name + content
                + struct.pack('!I', zlib.crc32(name + content)))

    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
    return raw


class ScaleTests(unittest.TestCase):
    def test_framework_lifecycle_and_real_clock(self):
        calls = []

        class Mode:
            def init(self):
                calls.append('init')

            def handle_events(self):
                calls.append('events')
                if calls.count('events') == 3:
                    game_framework.quit()

            def update(self):
                calls.append('update')
                self_test.assertGreaterEqual(game_framework.frame_time, 0)

            def render(self):
                calls.append('render')

            def finish(self):
                calls.append('finish')

        self_test = self
        game_framework.run(Mode())
        self.assertEqual(calls, ['init', 'events', 'update', 'render',
                                 'events', 'update', 'render', 'events', 'finish'])
        self.assertEqual(game_framework.stack, [])

    def test_approved_sizes_at_multiple_resolutions(self):
        for width, height in ((1280, 720), (1920, 1080), (2560, 1440), (1280, 1024)):
            arena, player, camera = scene(width, height)
            ppm = camera.pixels_per_meter
            self.assertAlmostEqual(arena.radius * 2 * ppm, height * 1.75)
            self.assertAlmostEqual(player.height * ppm, height * .05)
            self.assertAlmostEqual(player.width / player.height, .5)
            self.assertEqual(camera.to_screen(0, 0), (width / 2, height / 2))

    def test_equal_elapsed_time_gives_equal_distance(self):
        for fps in (15, 30, 60, 144):
            for diagonal in (False, True):
                arena, player, camera = scene()
                key(player, pico2d.SDL_KEYDOWN, pico2d.SDLK_d)
                if diagonal:
                    key(player, pico2d.SDL_KEYDOWN, pico2d.SDLK_w)
                game_framework.frame_time = 1 / fps
                for _ in range(fps * 3):
                    player.update()
                self.assertAlmostEqual(hypot(player.x, player.y), 14 / 3.6 * 3)

    def test_irregular_frames_and_key_release(self):
        _, player, _ = scene()
        key(player, pico2d.SDL_KEYDOWN, pico2d.SDLK_d)
        for dt in (.005, .1, .023, .007, .2, .665):
            game_framework.frame_time = dt
            player.update()
        self.assertAlmostEqual(player.x, player.speed_mps)
        key(player, pico2d.SDL_KEYUP, pico2d.SDLK_d)
        before = player.x
        player.update()
        self.assertEqual(player.x, before)

    def test_every_corner_stays_inside_circle(self):
        arena, player, _ = scene()
        for step in range(360):
            angle = step * pi / 180
            x, y = arena.constrain_box(1000 * cos(angle), 1000 * sin(angle),
                                      player.width, player.height)
            for dx in (-player.width / 2, player.width / 2):
                for dy in (-player.height / 2, player.height / 2):
                    self.assertLessEqual(hypot(x + dx, y + dy), arena.radius + 1e-9)

    def test_lower_half_stays_inside_while_upper_half_can_cross(self):
        arena, player, _ = scene()
        self.assertAlmostEqual(player.boundary_height, player.height / 2)
        for step in range(360):
            angle = step * pi / 180
            player.x, player.y = player.constrain_position(
                1000 * cos(angle), 1000 * sin(angle))
            left, bottom, right, top = player.get_boundary_bb()
            self.assertAlmostEqual(top, player.y)
            for x in (left, right):
                for y in (bottom, top):
                    self.assertLessEqual(hypot(x, y), arena.radius + 1e-9)
        player.x, player.y = player.constrain_position(0, 1000)
        self.assertGreater(player.get_bb()[3], arena.radius)
        # 아래쪽은 발밑, 위쪽은 몸의 중앙이 원에 닿아야 한다.
        self.assertAlmostEqual(hypot(player.width / 2, player.y), arena.radius)
        player.x, player.y = player.constrain_position(0, -1000)
        self.assertAlmostEqual(hypot(player.width / 2, player.get_bb()[1]), arena.radius)

    def test_movement_uses_lower_half_at_boundary(self):
        arena, player, _ = scene()
        key(player, pico2d.SDL_KEYDOWN, pico2d.SDLK_w)
        game_framework.frame_time = 1 / 30
        for _ in range(600):
            player.update()
        self.assertGreater(player.get_bb()[3], arena.radius)
        left, bottom, right, top = player.get_boundary_bb()
        for x in (left, right):
            for y in (bottom, top):
                self.assertLessEqual(hypot(x, y), arena.radius + 1e-9)

    def test_camera_stays_centered_at_all_boundaries_and_resolutions(self):
        for width, height in ((1280, 720), (1920, 1080), (1280, 1024)):
            arena, player, camera = scene(width, height)
            for step in range(0, 360, 10):
                angle = step * pi / 180
                player.x, player.y = player.constrain_position(
                    1000 * cos(angle), 1000 * sin(angle))
                camera.follow(player)
                self.assertEqual(camera.to_screen(player.x, player.y),
                                 (width / 2, height / 2))
                left, bottom, right, top = player.get_boundary_bb()
                for x in (left, right):
                    for y in (bottom, top):
                        self.assertLessEqual(hypot(x, y), arena.radius + 1e-9)

    def test_camera_coordinate_roundtrip(self):
        arena, player, camera = scene()
        player.x, player.y = 0, 4
        camera.follow(player)
        self.assertEqual(camera.to_screen(player.x, player.y), (960, 540))
        player.x, player.y = 100, 100
        camera.follow(player)
        self.assertEqual((camera.x, camera.y), (100, 100))
        x, y = camera.to_world(*camera.to_screen(3, 5))
        self.assertAlmostEqual(x, 3)
        self.assertAlmostEqual(y, 5)

    def test_data_rejects_empty_cells_and_bad_references(self):
        source = json.loads((ROOT / 'data/scale.json').read_text(encoding='utf-8'))
        for value in (None, '', -1, float('nan'), float('inf')):
            data = copy.deepcopy(source)
            data['characters'][0]['height_ratio'] = value
            with self.assertRaises(ValueError):
                validate(data)
        source['characters'][0]['viewport_id'] = 'missing'
        with self.assertRaises(ValueError):
            validate(source)


class RenderTests(unittest.TestCase):
    def test_real_renderer_input_and_focus(self):
        pico2d.open_canvas(1280, 720)
        try:
            play_mode.init()
            play_mode.render()
            raw = capture_png(ROOT / 'shots/arena-center.png', 1280, 720)
            pixel = lambda x, y: tuple(raw[(y * 1280 + x) * 4:(y * 1280 + x) * 4 + 3])
            self.assertEqual(pixel(640, 354), (64, 208, 192))
            self.assertEqual(pixel(1, 1), (13, 20, 29))
            event = pico2d.Event(pico2d.SDL_KEYDOWN)
            event.key = pico2d.SDLK_w
            with patch.object(pico2d, 'get_events', return_value=[event]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=True):
                play_mode.handle_events()
            game_framework.frame_time = 1 / 60
            for _ in range(60):
                play_mode.update()
            self.assertAlmostEqual(play_mode.player.y, 14 / 3.6)
            self.assertEqual(play_mode.camera.to_screen(play_mode.player.x, play_mode.player.y),
                             (640, 360))
            with patch.object(pico2d, 'get_events', return_value=[]), \
                 patch.object(pico2d, 'SDL_GetKeyboardFocus', return_value=False):
                play_mode.handle_events()
            self.assertFalse(play_mode.player.pressed_keys)
            y = play_mode.player.y
            play_mode.update()
            self.assertEqual(play_mode.player.y, y)
            play_mode.player.x, play_mode.player.y = play_mode.player.constrain_position(100, 100)
            play_mode.camera.follow(play_mode.player)
            play_mode.render()
            boundary_raw = capture_png(ROOT / 'shots/arena-boundary.png', 1280, 720)
            def boundary_pixel(x, y):
                offset = (y * 1280 + x) * 4
                return tuple(boundary_raw[offset:offset + 3])
            self.assertEqual(boundary_pixel(640, 354), (64, 208, 192))
            self.assertIn(boundary_pixel(1278, 1), ((13, 20, 29), (23, 33, 43)))
            # 종료 이벤트가 프레임워크에 전달되는지도 확인한다.
            game_framework.running = True
            with patch.object(pico2d, 'get_events', return_value=[pico2d.Event(pico2d.SDL_QUIT)]):
                play_mode.handle_events()
            self.assertFalse(game_framework.running)
        finally:
            play_mode.finish()
            pico2d.close_canvas()
        self.assertTrue(all(not layer for layer in game_world.world))


if __name__ == '__main__':
    unittest.main()
