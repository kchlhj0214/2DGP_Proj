"""Shared layout, keyboard and mouse controls for the native game menus."""

from ctypes import byref, c_int
from dataclasses import dataclass
from pathlib import Path

import pico2d
from pico2d import pico2d as canvas

import game_audio


WIDTH, HEIGHT = 1280, 720
INK = (243, 230, 205)
MUTED = (178, 169, 168)
GOLD = (217, 174, 116)
LINE = (87, 67, 58)
PANEL = (22, 20, 26)


@dataclass(frozen=True)
class Choice:
    action: str
    label: str
    bounds: tuple

    def contains(self, x, y):
        left, bottom, right, top = self.bounds
        return left <= x <= right and bottom <= y <= top

    def track(self):
        return self.bounds[0] + 19, self.bounds[2] - 19


class MenuUI:
    def __init__(self):
        self.width, self.height = pico2d.get_canvas_width(), pico2d.get_canvas_height()
        self.scale = min(self.width / WIDTH, self.height / HEIGHT)
        self.x = (self.width - WIDTH * self.scale) / 2
        self.y = (self.height - HEIGHT * self.scale) / 2
        self.fonts = {}
        self.text_widths = {}

    def close(self):
        for font in self.fonts.values():
            pico2d.TTF_CloseFont(font.font)
        self.fonts.clear()
        self.text_widths.clear()

    def point(self, event):
        return ((event.x - self.x) / self.scale,
                (self.height - 1 - event.y - self.y) / self.scale)

    def rectangle(self, bounds, color, filled=True):
        left, bottom, right, top = bounds
        pico2d.draw_rectangle(self.x + left * self.scale, self.y + bottom * self.scale,
                              self.x + right * self.scale, self.y + top * self.scale,
                              *color, filled=filled)

    def dim(self, opacity):
        blend = c_int()
        pico2d.SDL_GetRenderDrawBlendMode(canvas.renderer, byref(blend))
        pico2d.SDL_SetRenderDrawBlendMode(canvas.renderer, pico2d.SDL_BLENDMODE_BLEND)
        try:
            pico2d.draw_rectangle(0, 0, self.width, self.height, 8, 8, 14, opacity, filled=True)
        finally:
            pico2d.SDL_SetRenderDrawBlendMode(canvas.renderer, blend.value)

    def panel(self, bounds):
        left, bottom, right, top = bounds
        self.rectangle((left + 6, bottom - 7, right + 6, top - 7), (9, 8, 13))
        self.rectangle(bounds, PANEL)
        self.rectangle(bounds, LINE, filled=False)
        self.rectangle((left, top - 3, right, top), GOLD)

    def text(self, x, y, text, size=22, color=INK, align='left'):
        if size not in self.fonts:
            path = Path(pico2d.__file__).parent / 'data' / 'ConsolaMalgun.ttf'
            self.fonts[size] = pico2d.load_font(str(path), max(1, round(size * self.scale)))
        font = self.fonts[size]
        offset = 0
        if align != 'left':
            key = size, text
            if key not in self.text_widths:
                width = c_int()
                pico2d.TTF_SizeUTF8(font.font, text.encode('utf-8'), byref(width), None)
                self.text_widths[key] = width.value
            offset = self.text_widths[key] / (2 if align == 'center' else 1)
        font.draw(self.x + x * self.scale - offset, self.y + y * self.scale, text, color)

    def choices(self, items, selected):
        for index, item in enumerate(items):
            active = index == selected
            left, bottom, right, top = item.bounds
            self.rectangle(item.bounds, (59, 39, 33) if active else (32, 27, 33))
            self.rectangle(item.bounds, GOLD if active else LINE, filled=False)
            if active:
                self.rectangle((left, bottom, left + 4, top), GOLD)
            if item.action == 'volume':
                self.draw_volume(item)
            else:
                self.text(left + 19, (top + bottom) / 2, item.label, 23)
                if active:
                    self.text(right - 18, (top + bottom) / 2, '›', 23, GOLD, 'right')

    def draw_volume(self, item):
        left, bottom, right, top = item.bounds
        self.text(left + 19, top - 23, item.label, 21)
        self.text(right - 19, top - 23, f'{game_audio.volume}%', 20, GOLD, 'right')
        start, end = item.track()
        thumb = start + (end - start) * game_audio.volume / 100
        self.rectangle((start, bottom + 16, end, bottom + 20), (86, 68, 66))
        self.rectangle((start, bottom + 16, thumb, bottom + 20), GOLD)
        self.rectangle((thumb - 3, bottom + 11, thumb + 3, bottom + 25), INK)


class MenuInput:
    def __init__(self):
        self.selected = 0
        self.dragging = False

    def reset(self, selected=0):
        self.selected = selected
        self.dragging = False

    def handle(self, event, ui, items):
        if event.type == pico2d.SDL_KEYDOWN:
            self.dragging = False
            key = event.key
            if key == pico2d.SDLK_ESCAPE:
                return 'back'
            if key in (pico2d.SDLK_DOWN, pico2d.SDLK_UP, pico2d.SDLK_TAB):
                self.selected = (self.selected + (-1 if key == pico2d.SDLK_UP else 1)) % len(items)
            current = items[self.selected].action
            if current == 'volume' and key in (pico2d.SDLK_LEFT, pico2d.SDLK_RIGHT):
                game_audio.set_volume(game_audio.volume + (5 if key == pico2d.SDLK_RIGHT else -5))
            elif current != 'volume' and key in (pico2d.SDLK_RETURN, pico2d.SDLK_KP_ENTER):
                return current

        if event.type == pico2d.SDL_MOUSEBUTTONUP and event.button == pico2d.SDL_BUTTON_LEFT:
            self.dragging = False
        if event.type in (pico2d.SDL_MOUSEMOTION, pico2d.SDL_MOUSEBUTTONDOWN):
            x, y = ui.point(event)
            if self.dragging and event.type == pico2d.SDL_MOUSEMOTION:
                self.adjust_volume(items[self.selected], x)
                return None
            for index, item in enumerate(items):
                if not item.contains(x, y):
                    continue
                self.selected = index
                if event.type == pico2d.SDL_MOUSEBUTTONDOWN and event.button == pico2d.SDL_BUTTON_LEFT:
                    if item.action != 'volume':
                        return item.action
                    self.dragging = True
                    self.adjust_volume(item, x)
                break
        return None

    @staticmethod
    def adjust_volume(item, x):
        start, end = item.track()
        game_audio.set_volume(100 * (x - start) / (end - start))
