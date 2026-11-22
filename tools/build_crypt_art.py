"""Bake the crypt floor, bridges and portcullis layers for the pico2d scene."""

import json
from math import ceil, cos, pi, sin
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / 'data' / f'{name}.json').read_text(encoding='utf-8'))


ART = next(row for row in read('presentation')['visuals'] if row['id'] == 'arena')
WORLD = read('scale')
WAVES = read('waves')
ENTRY = WAVES['settings'][0]
RADIUS = ART['ring_radius_px']
UNIT = RADIUS / (WORLD['viewports'][0]['height_m'] * WORLD['arenas'][0]['diameter_height_ratio'] / 2)
PITCH = ART['floor_y_ratio']
PORTAL = RADIUS + round(ENTRY['portal_offset_m'] * UNIT)
INNER = RADIUS - round(ENTRY['bridge_inset_m'] * UNIT)
BRIDGE = round(ART['bridge_width_m'] * UNIT / 2)
SIZE = (1254, 1130)
CENTER = (SIZE[0] // 2, SIZE[1] // 2)
DENSITY = ART['crypt_radius_px'] / RADIUS
OUTSIDE = (15, 21, 29)
SLATE = ((53, 62, 72), (57, 67, 77), (61, 69, 79), (64, 72, 83), (67, 76, 86))
BRICK = ((67, 73, 85), (76, 81, 94), (83, 88, 100), (88, 94, 104))
JOINT = (31, 40, 50)


def pixels(*values):
    return tuple(round(value * DENSITY) for value in values)


class PixelDraw:
    """Draw the shared layout grid at the same world pixel density as the actors."""

    def __init__(self, image):
        self.draw = ImageDraw.Draw(image)

    @staticmethod
    def coords(points):
        if isinstance(points[0], (int, float)):
            return pixels(*points)
        return [pixels(*point) for point in points]

    def line(self, points, fill, width=1):
        self.draw.line(self.coords(points), fill=fill, width=pixels(width)[0])

    def polygon(self, points, fill, outline=None):
        self.draw.polygon(self.coords(points), fill=fill, outline=outline, width=pixels(1)[0])

    def ellipse(self, bounds, fill=None, outline=None, width=1):
        self.draw.ellipse(pixels(*bounds), fill=fill, outline=outline, width=pixels(width)[0])

    def rectangle(self, bounds, fill, outline=None):
        self.draw.rectangle(pixels(*bounds), fill=fill, outline=outline, width=pixels(1)[0])

    def point(self, pos, fill):
        self.draw.point(pixels(*pos), fill=fill)


def shade(color, amount):
    return tuple(max(0, min(255, channel + amount)) for channel in color)


def project(x, y, height=0):
    return round(CENTER[0] + x), round(CENTER[1] + y * PITCH - height)


def arc(radius, start, end, height=0):
    return [project(radius * cos(angle / 180 * pi), radius * sin(angle / 180 * pi), height)
            for angle in (start + (end - start) * i / 5 for i in range(6))]


def ring(draw, outer, inner, start, end, color, height=0):
    top = arc(outer, start, end, height)
    floor = arc(inner, end, start, height)
    draw.polygon(top + floor, fill=color, outline=shade(color, -18))
    draw.line(floor, fill=shade(color, 12))


def ellipse(radius):
    return (*project(-radius, -radius), *project(radius, radius))


def moat(draw, rng):
    for radius in range(600, RADIUS, -3):
        strength = max(0, 29 - (radius - RADIUS) // 5)
        draw.ellipse(ellipse(radius), fill=tuple(a + strength * b // 10
                                                 for a, b in zip(OUTSIDE, (3, 12, 13))))
    for _ in range(3100):
        x, y = rng.randint(-596, 596), rng.randint(-590, 590)
        if (RADIUS + 5) ** 2 < x*x + y*y < 592**2:
            fade = max(0, 26 - (round((x*x + y*y)**.5) - RADIUS) // 5)
            sx, sy = project(x, y)
            color = shade((20, 34, 40), rng.randint(-2, fade))
            draw.line((sx, sy, sx + rng.randint(2, 16), sy), fill=color)


def floor(image, rng):
    layer = Image.new('RGB', image.size, (42, 48, 57))
    draw = PixelDraw(layer)
    draw.ellipse(ellipse(RADIUS), fill=(42, 48, 57))
    for row, y in enumerate(range(-RADIUS - 18, RADIUS, 24)):
        for x in range(-RADIUS - 48 + (row % 2) * 23, RADIUS, 46):
            c = rng.choice(SLATE)
            left, top = project(x, y)
            right, bottom = project(x + 45, y + 23)
            draw.polygon([(left+2, top), (right-2, top), (right, top+2), (right, bottom-2),
                          (right-2, bottom), (left, bottom), (left, top+2)], fill=c)
            draw.line((left+3, top+1, right-4, top+1), fill=shade(c, 9))
            draw.line((left+2, bottom-1, right-2, bottom-1), fill=shade(c, -10))
            for _ in range(48):
                px, py = rng.uniform(left+2, right-3), rng.uniform(top+2, bottom-2)
                draw.point((px, py), fill=shade(c, rng.randint(-16, 13)))
                if rng.randrange(8) == 0:
                    draw.line((px, py, px + 1.2, py + .4), fill=shade(c, -11), width=.4)
            if rng.randrange(7) == 0:
                draw.line([(left+14, top), (left+17, top+6), (left+22, top+8),
                           (left+25, top+14), (left+32, bottom)], fill=shade(c, -21))
    mask = Image.new('L', image.size)
    PixelDraw(mask).ellipse(ellipse(RADIUS), fill=255)
    image.paste(layer, (0, 0), mask)


def crest(draw):
    for radius, color in ((101, (78, 86, 96)), (96, (39, 48, 59)), (91, (73, 81, 91))):
        draw.ellipse(ellipse(radius), outline=color, width=2)
    for angle in range(0, 360, 30):
        ring(draw, 101, 91, angle-2, angle+2, (98, 103, 108))
    skull = [(-39,-9),(-34,-30),(-22,-41),(22,-41),(34,-30),(39,-9),(36,9),
             (24,18),(24,34),(-24,34),(-24,18),(-36,9)]
    draw.polygon([project(x+2, y+3) for x,y in skull], fill=(40, 47, 55))
    draw.polygon([project(x, y) for x,y in skull], fill=(106, 107, 107), outline=(126, 124, 118))
    for x in (-24, 12):
        draw.polygon([project(x, -12), project(x+15, -15), project(x+13, 1),
                      project(x+3, 3)], fill=(52, 60, 66))
    draw.polygon([project(-4, 12), project(0, 4), project(4, 12)], fill=(52, 60, 66))
    for x in (-14, -5, 5, 14):
        draw.line((project(x, 25), project(x, 34)), fill=(60, 65, 68), width=2)


def walls(draw, rng):
    for start in (0, 90, 180, 270):
        for angle in range(start + 5, start + 85, 4):
            end = min(angle+4, start+85)
            ring(draw, RADIUS+34, RADIUS-7, angle, end, (25, 36, 45), -6)
            h = 6 if start < 180 else 16
            ring(draw, RADIUS+24, RADIUS-1, angle, end, shade(rng.choice(BRICK), -21), h-7)
            ring(draw, RADIUS+23, RADIUS+3, angle, end, rng.choice(BRICK), h)
            if (angle - start) % 16 == 9:
                ring(draw, RADIUS+27, RADIUS+1, angle, min(angle+3, end), (102, 109, 115), h+6)
    for angle in range(5, 360, 8):
        if 4 < angle % 90 < 86:
            ring(draw, RADIUS-14, RADIUS-20, angle, angle+3, (99, 103, 108))


def bridges(draw, rng):
    for ux, uy in ((1,0),(0,1),(-1,0),(0,-1)):
        def point(distance, side, height=0):
            return project(ux*distance - uy*side, uy*distance + ux*side, height)

        def slab(start, end, a, b, color, z=0):
            draw.polygon([point(start,a,z), point(end,a,z), point(end,b,z), point(start,b,z)],
                         fill=color, outline=shade(color, -21))

        slab(INNER-4, PORTAL+21, -BRIDGE-8, BRIDGE+8, (28, 40, 48), -5)
        for index, start in enumerate(range(INNER-2, PORTAL+17, 14)):
            end = min(start+14, PORTAL+20)
            joint = 8 if index % 2 else -8
            for a,b in ((-BRIDGE,joint),(joint,BRIDGE)):
                c = rng.choice(BRICK)
                slab(start, end, a, b, c)
                draw.line((point(start+1,a+1), point(start+1,b-1)), fill=shade(c, 17))
            for a,b in ((-BRIDGE-5,-BRIDGE), (BRIDGE,BRIDGE+5)):
                slab(start, end, a, b, (106, 110, 119), 3)
        slab(PORTAL+7, PORTAL+38, -BRIDGE-3, BRIDGE+3, (26, 30, 40), 1)


def gate_ironwork(width, h):
    bars = Image.new('RGBA', pixels(width, h))
    iron = PixelDraw(bars)
    for x in range(4, width, 9):
        iron.polygon([(x-2, 0), (x+3, 0), (x+3, h-6), (x, h-1), (x-2, h-7)],
                     fill=(44, 49, 62), outline=(20, 25, 36))
        iron.line((x, 1, x, h-8), fill=(127, 128, 137), width=1)
    for y in (h//4, h*3//5, h-13):
        iron.rectangle((2, y, width-3, y+5), fill=(56, 63, 76), outline=(21,26,38))
        iron.line((3, y+1, width-4, y+1), fill=(104,109,119))
        for x in range(4, width, 9):
            iron.point((x, y+3), fill=(156,150,135))
    return bars


def gate_frame(width, h, rear=False):
    fw, fh = width+32, h+28
    frame = Image.new('RGBA', pixels(fw, fh))
    stone = PixelDraw(frame)
    outline = [(1,fh-1),(1,24),(10,9),(23,2),(fw-24,2),(fw-11,9),(fw-2,24),(fw-2,fh-1),
               (fw-17,fh-1),(fw-17,32),(fw-25,21),(24,21),(16,32),(16,fh-1)]
    stone.polygon(outline, fill=(49,57,71), outline=(26,31,43))
    brick = [shade(color, -9) for color in BRICK] if rear else BRICK
    for left, right in ((3,15),(fw-16, fw-4)):
        for y in range(26, fh-2, 8):
            stone.rectangle((left,y,right,min(y+6,fh-2)), fill=brick[(y//8) % len(brick)])
            stone.line((left,y,right-1,y), fill=shade(brick[3], 30))
        if not rear:
            x = (left + right)//2
            stone.polygon([(x-4,38),(x+4,38),(x+3,44),(x-3,44)], fill=(161,141,110))
            stone.polygon([(x-3,36),(x-5,30),(x-1,32),(x+2,23),(x+5,34),(x+3,37)],
                          fill=(86,191,178))
            stone.line((x,35,x+2,29), fill=(185,236,207), width=2)
    for x in range(17, fw-17, 10):
        stone.rectangle((x, 6, min(x+8, fw-18), 20), fill=brick[(x//10) % len(brick)])
        stone.line((x, 6, min(x+8, fw-18), 6), fill=shade(brick[3], 38))
    if rear:
        stone.line((17, 20, fw-18, 20), fill=(111, 116, 124), width=2)
    else:
        mid = fw//2
        stone.polygon([(mid-6,8),(mid+6,8),(mid+5,17),(mid+2,20),(mid-2,20),(mid-5,17)],
                      fill=(176,172,149))
        stone.rectangle((mid-4,12,mid-2,14), fill=JOINT)
        stone.rectangle((mid+2,12,mid+4,14), fill=JOINT)
    return frame, [pixels(*point) for point in outline]


def gate_view(cell, frame, outline, depth):
    depth_y, = pixels(depth)
    cx, cy = cell[0] / 2, cell[1] - ART['gate_anchor_from_bottom_px']

    def project_face(point):
        x, y = point
        return round(cx + x - frame.width / 2), round(cy + y - frame.height)

    structure = Image.new('RGBA', cell)
    if depth_y:
        stone = ImageDraw.Draw(structure)
        corners = [project_face(point) for point in outline]
        for first, second in zip(corners, corners[1:] + corners[:1]):
            x, y = first
            u, v = second
            color = (95, 101, 113) if abs(u - x) > abs(v - y) else (45, 53, 67)
            stone.polygon((first, second, (u, v + depth_y), (x, y + depth_y)),
                          fill=color, outline=(33, 42, 51))
    inverse = (1, 0, frame.width / 2 - cx, 0, 1, frame.height - cy)
    return structure, inverse


def side_gate_frames(cell, height, frames):
    """Right-hand arch in profile, with the opening facing left across the bridge."""
    x = cell[0] / (2 * DENSITY)
    ground = (cell[1] - ART['gate_anchor_from_bottom_px']) / DENSITY
    footing = round(ground + BRIDGE * PITCH)
    track_top = footing - height
    roof = round(ground - height - 23)
    masonry = Image.new('RGBA', cell)
    stone = PixelDraw(masonry)

    # A straight stone housing conceals the face of the arch and the far post.
    stone.rectangle((x + 2, roof + 5, x + 26, footing), fill=(47, 56, 70), outline=JOINT)
    for index, y in enumerate(range(roof + 15, footing - 4, 9)):
        color = BRICK[index % len(BRICK)]
        stone.rectangle((x + 5, y, x + 24, min(y + 7, footing - 4)), fill=color)
        stone.line((x + 5, y, x + 24, y), fill=shade(color, 19))
        if index % 2 == 0:
            stone.line((x + 13, y + 1, x + 13, min(y + 7, footing - 4)), fill=shade(color, -14))

    stone.rectangle((x - 2, roof + 5, x + 3, footing - 3), fill=(27, 34, 46))
    stone.line((x + 2, roof + 6, x + 2, footing - 4), fill=(119, 126, 139))
    stone.rectangle((x, roof + 4, x + 28, roof + 12), fill=(70, 77, 91), outline=JOINT)
    stone.rectangle((x + 3, roof, x + 25, roof + 5), fill=(103, 110, 122), outline=JOINT)
    stone.line((x + 4, roof + 1, x + 24, roof + 1), fill=(127, 134, 143))
    stone.rectangle((x, footing - 4, x + 28, footing), fill=(65, 72, 86), outline=JOINT)

    output = []
    for phase in range(frames):
        frame = masonry.copy()
        drop = height - round(height * phase / (frames - 1))
        if drop:
            iron = PixelDraw(frame)
            tip = track_top + drop
            iron.rectangle((x - 5, track_top, x, tip), fill=(49, 57, 70), outline=(21, 27, 37))
            iron.line((x - 4, track_top, x - 4, tip), fill=(133, 137, 146))
            for y in (tip - 5, tip - 16, tip - 29):
                if y > track_top:
                    iron.line((x - 5, y, x, y), fill=(163, 156, 141), width=2)
        output.append(frame)
    return output


def gate_images():
    height = round(ART['gate_height_m'] * UNIT)
    width = 2 * BRIDGE + 6
    bars = gate_ironwork(width, height)
    columns, frames = ART['gate_atlas_cols'], ART['gate_lift_frames']
    cell = pixels(120, 162)
    rows = ceil(len(WAVES['gates']) * frames / columns)
    atlas = Image.new('RGBA', (cell[0] * columns, cell[1] * rows))
    profile = side_gate_frames(cell, height, frames)
    for side, gate in enumerate(WAVES['gates']):
        direction = gate['id']
        if gate['x_ratio']:
            for phase, view in enumerate(profile):
                if direction == 'west':
                    view = view.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                row, column = divmod(side * frames + phase, columns)
                atlas.paste(view, (column * cell[0], row * cell[1]))
            continue
        frame, outline = gate_frame(width, height, rear=direction == 'south')
        structure, inverse = gate_view(cell, frame, outline, -10 if direction == 'south' else 0)
        for phase in range(frames):
            face = Image.new('RGBA', frame.size)
            lift = round(bars.height * phase / (frames - 1))
            if lift < bars.height:
                # Cut off the ironwork as it rises behind the lintel.
                remaining = bars.crop((0, lift, bars.width, bars.height))
                face.alpha_composite(remaining, ((frame.width - bars.width) // 2,
                                                  frame.height - bars.height))
            face.alpha_composite(frame)
            view = structure.copy()
            view.alpha_composite(face.transform(cell, Image.Transform.AFFINE, inverse))
            row, column = divmod(side * frames + phase, columns)
            atlas.paste(view, (column * cell[0], row * cell[1]))
    atlas.save(ROOT / ART['gate_atlas'], optimize=True)


def build():
    output = ROOT / ART['crypt_art']
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = Random(301)
    image = Image.new('RGB', pixels(*SIZE), OUTSIDE)
    draw = PixelDraw(image)
    moat(draw, rng)
    floor(image, rng)
    crest(draw)
    walls(draw, rng)
    bridges(draw, rng)
    image.save(output, optimize=True)
    gate_images()


if __name__ == '__main__':
    build()
