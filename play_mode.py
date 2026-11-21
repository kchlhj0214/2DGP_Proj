"""콜로세움 전투와 웨이브 디버그 모드."""

import sys

import pico2d

import game_framework
import game_world
from arena import Arena
from camera import Camera
from game_data import ARENAS, CHARACTERS, VIEWPORTS
from player import Player
from combat_data import SYSTEMS
from combat_hud import CombatHUD
from wave_manager import WaveManager
from impact_effects import ImpactEffects
from sprites import SpriteLibrary
from patch_autopilot import PatchRound

player = arena = camera = None
focused = True
paused = False
enemies = []
projectiles = []
waves = None
test_path = autopilot = None


def init():
    global player, arena, camera, focused, paused, enemies, projectiles, waves, autopilot
    finish()
    viewport = VIEWPORTS['main']
    camera = Camera(pico2d.get_canvas_width(), pico2d.get_canvas_height(), viewport['height_m'])
    arena = Arena(ARENAS['arena'], viewport, camera)
    arena.load_art()
    player = Player(CHARACTERS['player'], viewport, arena, camera)
    player.sprites = SpriteLibrary()
    player.effects = ImpactEffects(camera, load_media=True)
    game_world.add_object(arena, 0)
    game_world.add_object(player, 1)
    enemies, projectiles = [], []
    player.targets = enemies
    player.projectiles = projectiles
    waves = WaveManager(player, enemies, projectiles)
    game_world.add_object(waves, 0)
    waves.load()
    game_world.add_object(CombatHUD(sys.modules[__name__]), 2)
    focused = True
    paused = False
    autopilot = PatchRound(sys.modules[__name__], test_path) if test_path is not None else None


def handle_events():
    global focused, paused
    events = pico2d.get_events()
    if autopilot is not None:
        if any(event.type == pico2d.SDL_QUIT for event in events):
            game_framework.quit()
        return
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
        elif event.type == pico2d.SDL_KEYDOWN and focused and waves.handle_key(event.key):
            break
        elif focused and not paused:
            player.handle_event(event)


def update():
    if focused and not paused:
        # 실제 경과 시간을 버리지 않고 작게 나눠 회전 칼의 충돌 누락을 방지한다.
        elapsed = game_framework.frame_time
        remaining = elapsed
        effects = player.effects
        try:
            while remaining > 1e-10:
                stop = effects.stopped_for
                if stop > 1e-10:
                    frozen = min(remaining, stop)
                    effects.update(frozen)
                    remaining -= frozen
                    continue
                game_framework.frame_time = min(remaining, SYSTEMS['main']['step_s'])
                effects.update(game_framework.frame_time)
                game_world.update()
                for projectile in projectiles[:]:
                    if not projectile.active:
                        projectiles.remove(projectile)
                        game_world.remove_object(projectile)
                remaining -= game_framework.frame_time
        finally:
            game_framework.frame_time = elapsed
    camera.follow(player)
    if autopilot is not None:
        autopilot.update(game_framework.frame_time)


def render():
    pico2d.clear_canvas()
    pico2d.draw_rectangle(0, 0, camera.width_px, camera.height_px,
                          57, 43, 35, filled=True)
    game_world.render(draw_ground_effects)
    player.effects.draw()
    pico2d.update_canvas()


def draw_ground_effects():
    for enemy in enemies:
        enemy.draw_warning()
    beam = player.combat.beam
    if beam:
        beam.draw()


def pause():
    player.pause()


def resume():
    player.pause()


def finish():
    global player, arena, camera, enemies, projectiles, waves, autopilot
    game_world.clear()
    if player is not None:
        player.sprites = player.effects = None
        arena.art = ()
    player = arena = camera = None
    enemies = []
    projectiles = []
    waves = None
    autopilot = None
