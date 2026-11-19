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
    """Interpolate the marked bases of the source stones, clockwise from east."""
    def sample(angle):
        pos = angle % math.tau / math.tau * len(samples)
        i = int(pos)
        t = pos - i
        a,b,c,d = (samples[(i+j) % len(samples)] for j in (-1,0,1,2))
        return b + .5*t*(c-a+t*(2*a-5*b+4*c-d+t*(3*(b-c)+d-a)))
    return sample


def trace_wall_base(art, samples):
    """Snap the traced guide to the original brick/sand seam, preserving the masonry."""
    guide = shore_depths(samples)
    cx, cy = art.width / 2, art.height / 2
    rgb = art.load()
    radii = []
    resolution = 1536
    for index in range(resolution):
        angle = index * math.tau / resolution
        vx, vy = math.cos(angle), math.sin(angle)
        guess = guide(angle)
        # At the gates there is no continuous stone to follow.
        gate_distance = abs(math.sin(2*angle))
        if gate_distance < .045:
            radii.append(guess)
            continue
        def source(r):
            samples = [rgb[round(cx + vx*r - vy*side),round(cy + vy*r + vx*side)]
                       for side in (-2,-1,0,1,2)]
            return tuple(sum(pixel[c] for pixel in samples)/len(samples) for c in range(3))
        result, best = guess, 17.0
        for shift in range(-7,6):
            r = guess + shift
            inside, outside = source(r-2),source(r+2)
            # The front has a bright coping lip. Across the arena the vertical
            # courses sit in shadow; both are read from the painted image.
            if vy >= 0:
                score = outside[1]-inside[1] + .36*(outside[2]-inside[2])
            else:
                score = inside[0]-outside[0] + .33*(inside[1]-outside[1])
            score -= abs(shift)*2.1
            if score > best:
                result, best = r-.65, score
        blend = min(1, max(0, (gate_distance-.045)/.10))
        radii.append(guess+(result-guess)*blend)
    # Median across nearby rays to stop individual paint speckles pulling the edge.
    smooth = [sorted(radii[(i+j) % resolution] for j in (-2,-1,0,1,2))[2]
              for i in range(resolution)]
    return shore_depths(smooth)


def water():
    settings = SETTINGS['arena']
    scale = json.loads((ROOT/'data/scale.json').read_text(encoding='utf-8'))
    radius_m = scale['viewports'][0]['height_m']*scale['arenas'][0]['diameter_height_ratio']/2
    radius = settings['ring_radius_px']
    drop = settings['bank_drop_px']
    bridge = settings['bridge_width_m']*radius/radius_m
    with Image.open(ROOT/settings['art']) as source:
        art = source.convert('RGB')
    shore = trace_wall_base(art,settings['wall_base_px'])
    size = art.size
    wall_color = art.load()
    cx,cy = size[0]/2,size[1]/2
    texture = Image.new('RGBA',size)
    pixels = texture.load()
    limit = max(settings['wall_base_px']) + 8
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
            wall = 1.7 + drop*.75*front
            depth = r-radius
            grain = (x*31+y*17+x*y*13)%9
            if depth < wall:
                joint = (theta*radius + math.sin(theta*93)*1.1) % 13.8 < 1.0
                pct = max(0, depth) / wall
                sand = wall_color[round(cx+dx*(radius-4)/r),round(cy+dy*(radius-4)/r)]
                light = (1 - .54*pct) * (.89 if joint else 1)
                color = tuple(round(channel*light+grain*.28) for channel in sand)
                pixels[x,y] = (*color, min(255,round((depth+2)*125)))
                continue

            stone_dist = outer-r
            # Reflect the real lowest stone row, with ripples breaking the image.
            ripple = math.sin(dy*.41+math.sin(dx*.054)) + math.sin(dy*.19+dx*.11)
            reflect_at = theta + ripple*.005
            reflect_r = outer + min(34,stone_dist*.75) + 5
            reflected = wall_color[
                round(cx+reflect_r*math.cos(reflect_at)),
                round(cy+reflect_r*math.sin(reflect_at))]
            strength = .30*math.exp(-stone_dist/(9 + 8*max(0,-dy/r)))
            shade = 1 - .42*math.exp(-stone_dist/4.5) - .21*math.exp(-(depth-wall)/4)
            wet = (46,65,65)
            speckle = ripple*1.6 + grain*.34
            color = tuple(round((base*(1-strength) + reflected[i]*strength)*shade+speckle)
                          for i,base in enumerate(wet))
            pixels[x,y] = (*color,min(255,round(stone_dist*180)))
    draw = ImageDraw.Draw(texture)
    rng = random.Random(72)
    for _ in range(710):
        angle = rng.uniform(0,math.tau)
        near = (1+math.sin(angle))/2
        r = rng.uniform(radius+11,shore(angle)-6)
        x,y = cx+r*math.cos(angle),cy+r*math.sin(angle)
        span = rng.uniform(3,10+17*near)
        if all(pixels[round(x+d),round(y)][1] > 54
               and pixels[round(x+d),round(y)][2] > 48
               and abs(math.hypot(x+d-cx,y-cy)-radius) > drop+5 for d in (0,span/2,span)):
            # Low, broken, predominantly horizontal glints follow the floor perspective.
            color = rng.choice(('#4a615a','#4c645d','#455a54','#626e63'))
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
