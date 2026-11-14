"""도형으로 방어·패링·광선을 시험하는 근접 전투 훈련 모드."""

import sys

import pico2d

import game_framework
import game_world
from arena import Arena
from camera import Camera
from game_data import ARENAS, CHARACTERS, VIEWPORTS
from player import Player
from combat_data import ENEMIES, SPAWNS, SYSTEMS
from combat_hud import CombatHUD
from enemy import MeleeEnemy

player = arena = camera = None
focused = True
paused = False
enemies = []


def init():
    global player, arena, camera, focused, paused, enemies
    game_world.clear()
    viewport = VIEWPORTS['main']
    camera = Camera(pico2d.get_canvas_width(), pico2d.get_canvas_height(), viewport['height_m'])
    arena = Arena(ARENAS['arena'], viewport, camera)
    player = Player(CHARACTERS['player'], viewport, arena, camera)
    game_world.add_object(arena, 0)
    game_world.add_object(player, 1)
    enemies = [MeleeEnemy(row['id'], ENEMIES[row['enemy_id']], row['x_m'], row['y_m'], player)
               for row in SPAWNS.values()]
    player.targets = enemies
    for enemy in enemies:
        game_world.add_object(enemy, 1)
    game_world.add_object(CombatHUD(sys.modules[__name__]), 2)
    focused = True
    paused = False


def handle_events():
    global focused, paused
    events = pico2d.get_events()
    # pico2d.get_events는 WINDOWEVENT를 반환하지 않으므로 포커스를 조회한다.
    has_focus = bool(pico2d.SDL_GetKeyboardFocus())
    if focused and not has_focus:
        pause()
    focused = has_focus
    for event in events:
        if event.type == pico2d.SDL_QUIT:
            game_framework.quit()
        elif event.type == pico2d.SDL_KEYDOWN and event.key == pico2d.SDLK_ESCAPE:
            paused = not paused
            pause()
        elif event.type == pico2d.SDL_KEYDOWN and event.key == pico2d.SDLK_r and focused:
            init()
            break
        elif focused and not paused:
            player.handle_event(event)


def update():
    if focused and not paused:
        # 실제 경과 시간을 버리지 않고 작게 나눠 회전 칼의 충돌 누락을 방지한다.
        elapsed = game_framework.frame_time
        remaining = elapsed
        try:
            while remaining > 1e-10:
                game_framework.frame_time = min(remaining, SYSTEMS['main']['step_s'])
                game_world.update()
                remaining -= game_framework.frame_time
        finally:
            game_framework.frame_time = elapsed
    camera.follow(player)


def render():
    pico2d.clear_canvas()
    pico2d.draw_rectangle(0, 0, camera.width_px, camera.height_px,
                          13, 20, 29, filled=True)
    game_world.render()
    pico2d.update_canvas()


def pause():
    player.pause()


def resume():
    player.pause()


def finish():
    global player, arena, camera, enemies
    game_world.clear()
    player = arena = camera = None
    enemies = []
