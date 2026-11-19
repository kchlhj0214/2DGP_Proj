"""Prepare the sprite flash masks and independent 2D water layer for pico2d."""

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

from build_sprite_motion import CELL, DATA, Figure, poses


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {row['id']: row for row in json.loads(
    (ROOT/'data/presentation.json').read_text(encoding='utf-8'))['visuals']}


def sprites():
    settings = SETTINGS['sprites']
    atlas = ROOT/settings['atlas']
    directory = ROOT/settings['asset_dir']
    directory.mkdir(parents=True,exist_ok=True)
    for clip in json.loads(atlas.read_text(encoding='utf-8'))['clips']:
        action, actor = clip['action'], clip['actor']
        if action == 'deflected':
            # The game moves the real actor. Bake the recoil pose with no screen translation.
            frames = list(poses(DATA['clips'][action]))
            sheet = Image.new('RGBA',(CELL*len(frames),CELL*8))
            for direction in range(8):
                for i, pose in enumerate(frames):
                    frame = Figure(actor,direction,dict(pose,retreat=0),None).render()
                    sheet.paste(frame,(i*CELL,direction*CELL))
            sheet.save(directory/clip['file'],optimize=True)
        else:
            with Image.open(atlas.parent/clip['file']) as original:
                sheet = original.convert('RGBA')
        flash = Image.new('RGBA',sheet.size,'white')
        flash.putalpha(sheet.getchannel('A'))
        flash.save(directory/f'{actor}-{action}-flash.png',optimize=True)


def shore_depths(samples):
    """Trace the sandstone edge in the source painting, clockwise from east."""
    def sample(angle):
        pos = angle % math.tau / math.tau * len(samples)
        i = int(pos)
        t = pos - i
        a,b,c,d = (samples[(i+j) % len(samples)] for j in (-1,0,1,2))
        return b + .5*t*(c-a+t*(2*a-5*b+4*c-d+t*(3*(b-c)+d-a)))
    return sample


def water():
    settings = SETTINGS['arena']
    scale = json.loads((ROOT/'data/scale.json').read_text(encoding='utf-8'))
    radius_m = scale['viewports'][0]['height_m']*scale['arenas'][0]['diameter_height_ratio']/2
    radius = settings['ring_radius_px']
    drop = settings['bank_drop_px']
    bridge = settings['bridge_width_m']*radius/radius_m
    shore = shore_depths(settings['shore_px'])
    with Image.open(ROOT/settings['art']) as source:
        size = source.size
    cx,cy = size[0]/2,size[1]/2
    texture = Image.new('RGBA',size)
    pixels = texture.load()
    limit = max(settings['shore_px']) + 8
    for y in range(int(cy-limit),int(cy+limit)+1):
        for x in range(int(cx-limit),int(cx+limit)+1):
            dx,dy = (x-cx,y-cy)
            r = math.hypot(dx,dy)
            if not radius-2 <= r <= limit:
                continue
            theta = math.atan2(dy,dx)
            outer = shore(theta)
            if r > outer:
                continue
            front = max(0,dy/r)
            # Water is below the sand. The near edge exposes a dark stone face;
            # at the back that same face is hidden behind the island.
            wall = 2.8 + drop*front
            depth = r-radius
            grain = (x*31+y*17+x*y*13)%9
            if depth < wall:
                joint = abs((theta*radius + math.sin(theta*93)*1.1) % 13.8) < 1.0
                light = max(0,2-depth)*14 - (16 if joint else 0) + grain
                base = (141,106,73) if depth < 1.4 else (83,65,49)
                pixels[x,y] = (*tuple(max(0,int(c+light)) for c in base),255)
                continue

            stone_dist = outer-r
            # Shade against both banks and pick up warm reflection from the old stone.
            shade = 1 - .54*math.exp(-stone_dist/(4 + 6*max(0,-dy/r)))
            shade -= .23*math.exp(-(depth-wall)/4)
            warm = 10*math.exp(-stone_dist/10)
            wave = math.sin(dy*(.6-.15*dy/r)+math.sin(dx*.038))
            glint = 3*wave + 2*math.sin(dy*.28+dx*.13) + grain*.45
            base = (53+warm,74+warm*.38,71-warm*.43)
            color = tuple(max(0,int(c*shade+glint)) for c in base)
            # Let the original paving still define the outer silhouette.
            pixels[x,y] = (*color,min(255,round(stone_dist*90)))
    draw = ImageDraw.Draw(texture)
    rng = random.Random(72)
    for _ in range(1150):
        angle = rng.uniform(0,math.tau)
        near = (1+math.sin(angle))/2
        r = rng.uniform(radius+11,shore(angle)-6)
        x,y = cx+r*math.cos(angle),cy+r*math.sin(angle)
        span = rng.uniform(3,10+17*near)
        if all(pixels[round(x+d),round(y)][1] > 54
               and pixels[round(x+d),round(y)][2] > 48
               and abs(math.hypot(x+d-cx,y-cy)-radius) > drop+5 for d in (0,span/2,span)):
            # Low, broken, predominantly horizontal glints follow the floor perspective.
            color = rng.choice(('#4f655d','#52685f','#455c55','#687367'))
            for start,end in ((0,span*.44),(span*.58,span)):
                draw.line((x+start,y,x+end,y),fill=color)
    for side in range(4):
        angle = side*math.pi/2
        fx,fy = round(math.cos(angle)),round(math.sin(angle))
        outer = shore(angle)
        half = bridge*.5*(1 + .16*fy)
        def point(distance, offset):
            perspective = 1 + .10*fy*(distance-radius)/(outer-radius)
            return cx+fx*distance-fy*offset*perspective,cy+fy*distance+fx*offset*perspective
        def slab(a,b,left,right,color,outline=None):
            draw.polygon([point(a,left),point(a,right),point(b,right),point(b,left)],
                         fill=color,outline=outline)
        top = (radius-6,outer+8,-half-2,half+2)
        a,b,left,right = top
        corners = [point(a,left),point(a,right),point(b,right),point(b,left)]
        draw.polygon([(x+3,y+6) for x,y in corners],fill='#2c302a')
        draw.polygon([(x+1,y+3) for x,y in corners],fill='#634b38')
        slab(*top,'#6f5440','#4c3b31')
        steps = list(range(radius-5,round(outer)+7,12))
        for index,distance in enumerate(steps):
            finish = min(distance+12,outer+8)
            joint = half * (.28 if index % 2 else -.31)
            for left,right in ((-half,joint),(joint,half)):
                color = rng.choice(('#a17f5e','#ae8964','#947455','#b3926f'))
                slab(distance,finish,left,right,color,'#775b43')
                draw.line((point(distance+1,left+1),point(distance+1,right-1)),
                          fill='#c2a07b')
                for _ in range(7):
                    spot = point(rng.uniform(distance+2,max(distance+2,finish-2)),
                                 rng.uniform(left+1,right-1))
                    draw.point(spot,fill=rng.choice(('#9c7958','#ba9670','#a28261')))
            for left,right in ((-half-2,-half+3),(half-3,half+2)):
                slab(distance,finish,left,right,'#c39b72','#805e45')
    texture.save(ROOT/settings['water'],optimize=True)


if __name__ == '__main__':
    sprites()
    water()
