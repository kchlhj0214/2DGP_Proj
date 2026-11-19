"""Draw the 2D pixel figures and export animation strips. Pillow is authoring-only."""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'data/sprite_motion.json').read_text(encoding='utf-8'))
OUT = ROOT / 'art/sprite-review'
CELL = DATA['cell_px']
OX, OY = DATA['origin_px']
INK = '#25202a'
BONE = ('#726957', '#c3b695', '#eee1ba')
SKIN = ('#824937', '#ba7752', '#e6a46d')
BOOT = ('#33262b', '#5d3a32', '#906149')
GOLD = ('#64412d', '#b78343', '#f5ce7d')
STEEL = ('#4d5565', '#8397a8', '#d9e9e8')
CLOTH = ('#3a2235', '#613248', '#9c4f60')


def validate():
    columns = DATA['motion_columns']
    assert len(set(columns)) == len(columns)
    assert len(set(DATA['directions'])) == 8
    for name, clip in DATA['clips'].items():
        frames = clip['frames']
        assert set(clip['actors']) <= set(DATA['actors']), name
        assert frames[0][0] == 0 and all(a[0] < b[0] for a, b in zip(frames, frames[1:])), name
        for row in frames:
            assert len(row) == len(columns) and all(math.isfinite(x) for x in row), name
        if clip['loop']:
            assert frames[0][1:] == frames[-1][1:], name
    # The blocked branch starts from precisely the same pose as the descending blade.
    chop = DATA['clips']['chop']['frames']
    contact = DATA['clips']['deflected']['frames'][0]
    assert sum(row[1:] == contact[1:] for row in chop) == 1


def poses(clip):
    rows = clip['frames']
    if len(rows) == 1:
        yield dict(zip(DATA['motion_columns'], rows[0]))
        return
    for a, b in zip(rows, rows[1:]):
        for frame in range(a[0], b[0]):
            fraction = (frame - a[0]) / (b[0] - a[0])
            values = [x + (y - x) * fraction for x, y in zip(a, b)]
            yield dict(zip(DATA['motion_columns'], values))
    if not clip['loop']:
        yield dict(zip(DATA['motion_columns'], rows[-1]))


class Figure:
    """Draw flat pixel shapes with direction-specific offsets and paint order."""

    def __init__(self, actor, direction, pose):
        self.image = Image.new('RGBA', (CELL, CELL))
        self.draw = ImageDraw.Draw(self.image)
        angle = direction * math.tau / 8
        self.fx, self.fy = math.sin(angle), math.cos(angle)
        self.actor, self.pose = actor, pose
        self.back = self.fy < -.4
        self.profile = abs(self.fx) > .9
        self.width = .7 + .3 * abs(self.fy)
        self.near = -1 if self.fx > 0 else 1
        self.ground = -pose['retreat']

    def point(self, side, forward, up):
        x = OX + self.fy * side + self.fx * (forward + self.ground)
        y = OY + .43 * (-self.fx * side + self.fy * (forward + self.ground)) - up
        return round(x), round(y)

    def poly(self, points, fill, outline=INK):
        self.draw.polygon([(round(x), round(y)) for x, y in points], fill=fill, outline=outline)

    def oval(self, x, y, rx, ry, color, outline=INK):
        self.draw.ellipse((round(x-rx), round(y-ry), round(x+rx), round(y+ry)),
                          fill=color, outline=outline)

    def segment(self, a, b, width, colors):
        width = round(width)
        self.draw.line((a, b), fill=INK, width=width+2)
        self.oval(*b, width/2, width/2, colors[0])
        self.draw.line((a, b), fill=colors[1], width=width)
        offset = max(1, width//4)
        bright_a = (a[0]-offset, a[1]-1)
        bright_b = (b[0]-offset, b[1]-1)
        self.draw.line((bright_a, bright_b), fill=colors[2], width=1)

    def leg(self, side):
        p = self.pose
        stride = p['stride'] * side
        lift = max(0, (abs(p['stride']) - 3) * .22) if stride > 0 else 0
        hip = self.point(6*side, p['lean']*.25, 29-p['crouch'])
        knee = self.point(7*side, stride*.54 + p['knee'], 16-p['crouch']*.5+lift*.4)
        ankle = self.point(8*side, stride, 4+lift)
        toe = self.point(8*side, stride+5, 2+lift)
        flesh = self.actor == 'hero'
        self.segment(hip, knee, 8 if flesh else 4, SKIN if flesh else BONE)
        self.segment(knee, ankle, 6 if flesh else 3, BOOT if flesh else BONE)
        self.segment(ankle, toe, 7 if flesh else 4, BOOT if flesh else BONE)
        if flesh:
            self.draw.line((knee[0]-3, knee[1], knee[0]+3, knee[1]), fill='#bc9a74', width=2)

    def torso(self, shoulder, hips):
        sx, sy = shoulder
        hx, hy = hips
        w = (14 if self.actor == 'hero' else 10)*self.width
        if self.actor == 'ranged':
            flutter = self.pose['stride']*.28
            hem = hy + 19
            self.poly([(sx-w,sy), (sx+w,sy), (hx+11+flutter,hem-1),
                       (hx+3,hem+3), (hx-4,hem), (hx-13+flutter,hem+2)], CLOTH[1])
            self.poly([(sx-4,sy+3), (hx-7+flutter,hem), (hx-2,hem-2), (hx+1,hy)], CLOTH[2], None)
            self.draw.line((sx-4,sy+3,sx+5,sy+3), fill=GOLD[2], width=2)
            return
        if self.actor == 'hero':
            self.poly([(sx-w,sy+1),(sx-w+4,sy-4),(sx+w-4,sy-4),(sx+w,sy+1),
                       (hx+8,hy-6),(hx+7,hy),(hx-8,hy),(hx-9,hy-5)], SKIN[1])
            self.poly([(sx-w+2,sy+2),(sx-2,sy-3),(sx+1,sy+2),
                       (sx+w-3,sy),(sx+w-5,sy+6),(sx-1,sy+6),(sx-6,sy+7)], SKIN[2], None)
            self.draw.line((sx,sy+8,hx-1,hy-5), fill=SKIN[0], width=2)
            self.draw.line((hx-5,hy-6,hx+3,hy-6), fill=SKIN[2])
        else:
            self.segment((sx,sy), (hx,hy-2), 4, BONE)
            for i in range(4):
                y = sy+3+i*3
                r = w-i
                self.draw.line([(round(sx-r),y-1),(sx,y+2),(round(sx+r),y-1)], fill=BONE[0], width=3)
                self.draw.line([(round(sx-r),y-2),(sx,y+1),(round(sx+r),y-2)], fill=BONE[2])
        fabric = BOOT if self.actor == 'hero' else CLOTH
        self.poly([(hx-9,hy-1),(hx+9,hy-1),(hx+12,hy+10),
                   (hx+5,hy+8),(hx,hy+12),(hx-5,hy+8),(hx-11,hy+10)], fabric[1])
        self.poly([(hx-6,hy+1),(hx-1,hy+1),(hx-3,hy+8),(hx-8,hy+8)], fabric[2], None)
        self.draw.line((hx-8,hy,hx+8,hy), fill=GOLD[0], width=3)
        if not self.back:
            self.draw.rectangle((hx-2,hy-1,hx+2,hy+2), fill=GOLD[1])
            self.draw.point((hx-1,hy-1), fill=GOLD[2])

    def head(self, x, y):
        self.oval(x, y, 8, 9, SKIN[1] if self.actor == 'hero' else BONE[1])
        if self.actor == 'ranged':
            self.poly([(x-10,y+5),(x-9,y-6),(x-3,y-12),(x+4,y-11),
                       (x+9,y-5),(x+10,y+8),(x+5,y+10),(x-5,y+9)], CLOTH[1])
            self.draw.line((x-8,y-5,x-3,y-10,x+4,y-10), fill=CLOTH[2], width=2)
            if not self.back:
                self.oval(x,y+1,6 if not self.profile else 4,7,INK)
                self.oval(x,y+3,4,4,BONE[1],None)
                self.draw.line((x-3,y,x+3,y), fill='#cb86ee', width=2)
            return
        if self.actor == 'hero':
            pony = x-round(self.fx*9)-3
            self.poly([(pony,y-7),(pony-4,y-3),(pony-2,y+8),(pony+3,y+5),(pony+4,y-6)], BOOT[0])
            self.poly([(x-8,y-1),(x-8,y-6),(x-4,y-10),(x+4,y-10),(x+8,y-5),
                       (x+7,y+4),(x-7,y+5)], BOOT[1])
            self.draw.line((x-5,y-7,x+3,y-8,x+6,y-5), fill=BOOT[2], width=2)
            if not self.back:
                face = x+round(self.fx*3)
                self.poly([(face-5,y-3),(face+4,y-3),(face+5,y+2),
                           (face+3,y+6),(face-3,y+6),(face-5,y+3)], SKIN[1], None)
                self.draw.line((face-4,y+4,face-1,y+8,face+3,y+7,face+5,y+4), fill=BOOT[0], width=2)
                self.draw.line((face-4,y-1,face+3,y-1), fill=INK)
                self.draw.point((face+1,y+2), fill=SKIN[2])
            return
        if not self.back:
            eye = x+round(self.fx*3)
            self.draw.line((eye-4,y,eye+4,y), fill=INK, width=3)
            self.draw.point((eye+2,y), fill='#d999ef')
            for dx in (-3,0,3):
                self.draw.line((x+dx,y+5,x+dx,y+7), fill=BONE[0])
        self.poly([(x-9,y-1),(x-8,y-7),(x-5,y-10),(x+4,y-11),
                   (x+8,y-6),(x+9,y-2),(x+3,y-3),(x-3,y-3)], GOLD[1])
        self.draw.line((x-7,y-5,x-4,y-8,x+3,y-9), fill=GOLD[2], width=2)

    def arm(self, side):
        p = self.pose
        shoulder = self.point(side*13, p['lean'], 49-p['crouch'])
        equipment = side == (1 if self.actor == 'hero' else -1)
        forward = -p['stride']*.48 if side == 1 else p['stride']*.48
        lift = 0
        if equipment:
            if self.actor == 'hero':
                forward, lift = p['shield_forward'], p['shield_up']
            else:
                forward, lift = p['blade_forward'], p['blade_up']
        hand = self.point(side*14, forward + p['lean']*.25, 26+lift-p['crouch'])
        elbow = self.point(side*17, (forward+p['lean'])*.38-3,
                           39+lift*.35-p['crouch'])
        flesh = self.actor == 'hero'
        colors = SKIN if flesh else CLOTH if self.actor == 'ranged' else BONE
        thickness = 7 if flesh or self.actor == 'ranged' else 3
        self.segment(shoulder, elbow, thickness, colors)
        self.segment(elbow, hand, thickness-1, colors)
        if self.actor == 'melee' and side == 1:
            x, y = shoulder
            for dy in (4,2,0):
                self.oval(x,y+dy,7-dy//2,3,STEEL[1],GOLD[0])
        if equipment:
            if flesh:
                self.shield(hand)
            else:
                self.weapon(hand)
        elif self.actor == 'ranged' and p['cast'] >= 2:
            x, y = hand
            self.poly([(x-4,y-5),(x,y-9),(x+4,y-5),(x,y-1)], '#e6b5fa', '#9d55d6')

    def shield(self, center):
        x, y = center
        # Side-facing while relaxed. Turn the face toward the attack when raised.
        aim = min(1, max(0, (self.pose['shield_forward']-6)/11))
        normal = -self.fx*(1-aim)+self.fy*aim
        w = 6+8*abs(normal)
        self.oval(x,y, w+2,15,GOLD[0])
        self.oval(x,y-1,w+1,14,GOLD[2])
        self.oval(x,y,w-1,12,'#775037' if normal < -.15 else '#434356')
        self.draw.line((x-round(w)+2,y,x+round(w)-2,y), fill=GOLD[1], width=3)
        self.draw.line((x,y-10,x,y+10), fill=GOLD[1], width=2)
        if normal >= -.15:
            self.oval(x,y,3,3,'#5dd5c1',GOLD[2])
            self.draw.point((x-1,y-1), fill='#c9fff2')
        for dx,dy in ((-.6,-6),(.6,-6),(-.6,6),(.6,6)):
            self.draw.point((round(x+w*dx),y+dy), fill=GOLD[2])

    def weapon(self, grip):
        angle = math.radians(self.pose['blade_angle'])
        dx = self.fx*math.cos(angle)
        dy = self.fy*.43*math.cos(angle)-math.sin(angle)
        length = max(.1, math.hypot(dx,dy))
        nx, ny = -dy/length, dx/length
        def point(along, across=0):
            return grip[0]+dx*along+nx*across, grip[1]+dy*along+ny*across
        if self.actor == 'ranged':
            a, b = point(-23), point(23)
            self.draw.line((a,b), fill=INK, width=5)
            self.draw.line((a,b), fill=BOOT[2], width=2)
            x,y = point(26)
            self.poly([(x,y-8),(x+5,y-3),(x+4,y+4),(x,y+7),(x-5,y)], '#9951c2')
            self.poly([(x,y-6),(x+1,y+3),(x-4,y)], '#efb8fc', None)
            if self.pose['cast'] >= 2:
                self.oval(x,y,9,8,None,'#b775dc')
            return
        self.poly([point(-7,-2),point(5,-2),point(5,2),point(-7,2)], BOOT[2])
        self.oval(*point(-7), 2,2,GOLD[1])
        self.poly([point(5,-3),point(29,-2),point(36),point(29,2),point(5,3)], STEEL[1])
        self.poly([point(6),point(36),point(28,-2),point(6,-2)], STEEL[2], None)
        self.poly([point(3,-7),point(6,-6),point(6,6),point(3,7)], GOLD[1])
        self.draw.point(tuple(round(k) for k in grip), fill=BONE[2])

    def render(self):
        p = self.pose
        for side in (-self.near,self.near):
            self.leg(side)
        self.arm(-self.near)
        shoulder = self.point(0,p['lean'],50-p['crouch'])
        hips = self.point(0,p['lean']*.25,29-p['crouch'])
        self.torso(shoulder,hips)
        self.head(*self.point(0,p['lean']+2,61-p['crouch']))
        self.arm(self.near)
        return self.image


def build():
    validate()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        'fps': DATA['fps'], 'origin_px': DATA['origin_px'], 'cell_px': CELL,
        'directions': DATA['directions'], 'clips': [],
    }
    for name, clip in DATA['clips'].items():
        frames = list(poses(clip))
        for actor in clip['actors']:
            sheet = Image.new('RGBA', (CELL*len(frames),CELL*len(DATA['directions'])))
            for direction in range(len(DATA['directions'])):
                for i, pose in enumerate(frames):
                    canvas = Figure(actor,direction,pose).render()
                    bbox = canvas.getbbox()
                    assert bbox and 0 < bbox[0] < bbox[2] < CELL and 0 < bbox[1] < bbox[3] < CELL, (
                        actor, name, direction, i, bbox
                    )
                    sheet.paste(canvas, (CELL*i,CELL*direction))
            path = f'{actor}-{name}.png'
            sheet.save(OUT/path, optimize=True)
            manifest['clips'].append({
                'actor': actor, 'action': name, 'file': path, 'frames': len(frames),
                'loop': clip['loop'],
            })
    (OUT/'atlas.json').write_text(json.dumps(manifest,indent=2)+'\n', encoding='utf-8')
    print(f"Exported {len(manifest['clips'])} sheets in {len(DATA['directions'])} directions.")


if __name__ == '__main__':
    build()
