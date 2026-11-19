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


def water():
    settings = SETTINGS['arena']
    scale = json.loads((ROOT/'data/scale.json').read_text(encoding='utf-8'))
    radius_m = scale['viewports'][0]['height_m']*scale['arenas'][0]['diameter_height_ratio']/2
    radius = settings['ring_radius_px']
    width = settings['water_width_m']*radius/radius_m
    bridge = settings['bridge_width_m']*radius/radius_m
    with Image.open(ROOT/settings['art']) as source:
        size = source.size
    cx,cy = size[0]/2,size[1]/2
    texture = Image.new('RGBA',size)
    pixels = texture.load()
    outer = radius+width
    for y in range(int(cy-outer-2),int(cy+outer+3)):
        for x in range(int(cx-outer-2),int(cx+outer+3)):
            dx,dy = (x-cx,y-cy)
            depth = math.hypot(dx,dy)-radius
            if not 0 <= depth <= width:
                continue
            waves = math.sin(dy*.34+math.sin(dx*.07))+math.sin(dy*.73-dx*.13)
            speckle = ((x*317+y*79+x*y*13)%11)/3
            if depth < 4 or depth > width-4:
                color = (76,64,48) if 1.5 < depth < width-1.5 else (116,93,65)
            else:
                light = 4*waves+speckle+max(0,5-depth*.2)
                color = tuple(int(c+light) for c in (27,67,77))
            pixels[x,y] = (*color,255)
    draw = ImageDraw.Draw(texture)
    rng = random.Random(72)
    for _ in range(360):
        u = rng.uniform(0,math.tau)
        r = radius+rng.uniform(7,width-7)
        x,y = cx+r*math.cos(u),cy+r*math.sin(u)
        span = rng.randint(2,8)
        if radius+4 < math.hypot(x+span-cx,y-cy) < outer-4:
            draw.line((x,y,x+span,y),fill=rng.choice(('#386772','#4c7479','#315865')))
    for side in range(4):
        angle = side*math.pi/2
        fx,fy = round(math.cos(angle)),round(math.sin(angle))
        def point(distance, offset):
            return (cx+fx*distance-fy*offset,cy+fy*distance+fx*offset)
        def plank(a,b,left,right,color,outline=None):
            draw.polygon([point(a,left),point(a,right),point(b,right),point(b,left)],
                         fill=color,outline=outline)
        half = bridge*.5
        plank(radius-6,outer+9,-half-5,half+5,'#453329','#2e2723')
        for distance in range(radius-5,int(outer+8),6):
            plank(distance,distance+5,-half,half,rng.choice(('#a57b50','#9b7149','#af8357')),'#694d37')
            draw.line((point(distance+1,-half+3),point(distance+1,half-3)),fill='#bb8c5d')
        for offset in (-half-1,half+1):
            draw.line((point(radius-7,offset),point(outer+8,offset)),fill='#574029',width=4)
            for distance in (radius-7,radius+width*.48,outer+8):
                x,y = point(distance,offset)
                draw.ellipse((x-3,y-3,x+3,y+3),fill='#9a7350',outline='#49392d')
    texture.save(ROOT/settings['water'],optimize=True)


if __name__ == '__main__':
    sprites()
    water()
