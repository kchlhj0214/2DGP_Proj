"""도형으로 맵과 플레이어의 크기 및 이동을 확인하는 모드."""

import pico2d

import game_framework
import game_world
from arena import Arena
from camera import Camera
from game_data import ARENAS, CHARACTERS, VIEWPORTS
from player import Player

player = arena = camera = None
focused = True


def init():
    global player, arena, camera, focused
    game_world.clear()
    viewport = VIEWPORTS['main']
    camera = Camera(pico2d.get_canvas_width(), pico2d.get_canvas_height(), viewport['height_m'])
    arena = Arena(ARENAS['arena'], viewport, camera)
    player = Player(CHARACTERS['player'], viewport, arena, camera)
    game_world.add_object(arena, 0)
    game_world.add_object(player, 1)
    focused = True


def handle_events():
    global focused
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
            game_framework.quit()
        elif focused:
            player.handle_event(event)


def update():
    if focused:
        game_world.update()
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
    global player, arena, camera
    game_world.clear()
    player = arena = camera = None
