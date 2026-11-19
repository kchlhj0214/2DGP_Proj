"""Draw the 2D pixel figures and export animation strips. Pillow is authoring-only."""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'data/sprite_motion.json').read_text(encoding='utf-8'))
OUT = ROOT / 'art/sprite-review'
CELL = DATA['cell_px']
SCALE = DATA['drawing_scale']
OX, OY = [value / SCALE for value in DATA['origin_px']]
INK = '#241d24'
BONE = ('#806b55', '#beaa8b', '#ead7b1')
SKIN = ('#8b5641', '#bc825d', '#e0a77e')
BOOT = ('#362720', '#634638', '#946f53')
GOLD = ('#563a2b', '#a2754c', '#d5ab77')
STEEL = ('#4e4949', '#817a77', '#c8bcb1')
CLOTH = ('#362329', '#623d46', '#90636a')


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
        if 'shield_pitch_deg' in clip:
            pitches = clip['shield_pitch_deg']
            assert len(pitches) == len(frames) and all(0 <= pitch <= 90 for pitch in pitches), name
        if clip['loop']:
            assert frames[0][1:] == frames[-1][1:], name
    for name, gait in DATA['gaits'].items():
        clip = DATA['clips'][name]
        assert clip['loop'] and len(gait) == clip['frames'][-1][0] and len(gait) % 2 == 0
        assert all(len(row) == len(DATA['gait_columns']) and all(math.isfinite(v) for v in row)
                   for row in gait), name
    # The blocked branch starts from precisely the same pose as the descending blade.
    chop = DATA['clips']['chop']['frames']
    contact = DATA['clips']['deflected']['frames'][0]
    assert sum(row[1:] == contact[1:] for row in chop) == 1


def poses(clip):
    pitches = clip.get('shield_pitch_deg',[0]*len(clip['frames']))
    rows = [row+[pitch] for row,pitch in zip(clip['frames'],pitches)]
    columns = DATA['motion_columns']+['shield_pitch_deg']
    if len(rows) == 1:
        yield dict(zip(columns,rows[0]))
        return
    for a, b in zip(rows, rows[1:]):
        for frame in range(a[0], b[0]):
            fraction = (frame - a[0]) / (b[0] - a[0])
            values = [x + (y - x) * fraction for x, y in zip(a, b)]
            yield dict(zip(columns,values))
    if not clip['loop']:
        yield dict(zip(columns,rows[-1]))


class PixelBrush:
    """Rasterize paths at the target pixel size, with no filtering."""
    def __init__(self, image):
        self.canvas = ImageDraw.Draw(image)

    def path(self, coordinates):
        if isinstance(coordinates[0], (tuple, list)):
            return [self.path(point) for point in coordinates]
        return tuple(round(v*SCALE) for v in coordinates)

    def line(self, coordinates, fill, width=1):
        self.canvas.line(self.path(coordinates), fill=fill, width=max(1, round(width*SCALE)))

    def rectangle(self, box, **options):
        self.canvas.rectangle(self.path(box), **options)

    def ellipse(self, box, **options):
        self.canvas.ellipse(self.path(box), **options)

    def polygon(self, coordinates, **options):
        self.canvas.polygon(self.path(coordinates), **options)

    def point(self, coordinates, fill):
        self.canvas.point(self.path(coordinates), fill)


class ShieldBrush(PixelBrush):
    """Map the painted shield face onto two projected axes around the grip."""

    def __init__(self, brush, center, across, down):
        self.canvas = brush.canvas
        self.center = center
        self.across = across
        self.down = down

    def path(self, coordinates):
        if isinstance(coordinates[0], (tuple,list)):
            return [self.path(point) for point in coordinates]
        result = []
        cx,cy = self.center
        for x,y in zip(coordinates[::2],coordinates[1::2]):
            u,v = x-cx,y-cy
            result.extend((round((cx+u*self.across[0]+v*self.down[0])*SCALE),
                           round((cy+u*self.across[1]+v*self.down[1])*SCALE)))
        return tuple(result)

    def ellipse(self, box, **options):
        left,top,right,bottom = box
        x,y = (left+right)*.5,(top+bottom)*.5
        rx,ry = (right-left)*.5,(bottom-top)*.5
        angles = (i*math.tau/40 for i in range(40))
        self.polygon([(x+rx*math.cos(a),y+ry*math.sin(a)) for a in angles],**options)


class Figure:
    """Draw flat pixel shapes with direction-specific offsets and paint order."""

    def __init__(self, actor, direction, pose, gait):
        self.image = Image.new('RGBA', (CELL, CELL))
        self.draw = PixelBrush(self.image)
        angle = direction * math.tau / 8
        self.fx, self.fy = math.sin(angle), math.cos(angle)
        self.actor, self.pose = actor, pose
        self.gait = gait
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
        self.draw.polygon(points, fill=fill, outline=outline)

    def oval(self, x, y, rx, ry, color, outline=INK):
        self.draw.ellipse((x-rx,y-ry,x+rx,y+ry),fill=color,outline=outline)

    def segment(self, a, b, width, colors):
        ax, ay = a
        bx, by = b
        distance = math.hypot(bx-ax,by-ay)
        if distance < 1:
            self.oval(ax,ay,width*.5,width*.5,colors[1])
            return
        nx, ny = (by-ay)/distance, (ax-bx)/distance
        if nx > 0:
            nx, ny = -nx, -ny
        def cross(x, y, offset):
            return x+nx*offset, y+ny*offset
        radius = width*.5
        end = radius*.72
        self.poly([cross(ax,ay,-radius),cross(ax,ay,radius),
                   cross(bx,by,end),cross(bx,by,-end)], colors[1])
        self.poly([cross(ax,ay,-radius+.6),cross(ax,ay,-radius*.25),
                   cross(bx,by,0),cross(bx,by,-end+.7)], colors[0], None)
        self.draw.line((cross(ax,ay,radius*.5),cross(bx,by,end*.35)), fill=colors[2])
        self.oval(bx,by,end,end,colors[1],None)

    def foot_pose(self, side):
        phase = int(self.pose['frame']) + (len(self.gait)//2 if side < 0 else 0)
        return self.gait[phase % len(self.gait)]

    def boot(self, ankle, toe):
        x,y = ankle
        tx,ty = toe
        sign = 1 if tx>=x else -1
        if abs(tx-x) < 2:
            # Cap and sole seen from the front or back.
            self.poly([(x-3,y-1),(x+3,y-1),(x+4,ty+1),(x+3,ty+4),
                       (x-3,ty+4),(x-4,ty+2)],BOOT[1])
            self.draw.line((x-3,ty+3,x+3,ty+3),fill=BOOT[0],width=2)
            self.draw.line((x-2,ty,x+1,ty),fill=BOOT[2])
            return
        self.poly([(x-3*sign,y-3),(x+2*sign,y-2),(tx,ty-1),
                   (tx+2*sign,ty+1),(tx+sign,ty+3),(x-3*sign,y+3)],BOOT[1])
        self.draw.line((x-2*sign,y+2,tx+sign,ty+2),fill=BOOT[0],width=2)
        self.draw.line((x+sign,y-1,tx,ty),fill=BOOT[2])

    def leg(self, side):
        p = self.pose
        hip_forward, hip_up = p['lean']*.25, 29-p['crouch']
        if self.gait:
            stride, lift, pitch, _ = self.foot_pose(side)
            dx, dy = stride-hip_forward, 4+lift-hip_up
            distance = math.hypot(dx,dy)
            bend = math.sqrt(max(0, 15**2-(distance*.5)**2))
            knee_forward = hip_forward+dx*.5-dy*bend/max(distance,1)
            knee_up = hip_up+dy*.5+dx*bend/max(distance,1)
        else:
            stride = p['stride'] * side
            lift = max(0,(abs(stride)-3)*.22) if stride > 0 else 0
            pitch = 0
            knee_forward = stride*.54+p['knee']
            knee_up = 16-p['crouch']*.5+lift*.4
        hip = self.point(6*side, hip_forward, hip_up)
        knee = self.point(7*side, knee_forward, knee_up)
        ankle = self.point(8*side, stride, 4+lift)
        toe = self.point(8*side, stride+5, max(1,2+lift+pitch))
        flesh = self.actor == 'hero'
        self.segment(hip, knee, 10 if flesh else 4, SKIN if flesh else BONE)
        self.segment(knee, ankle, 7 if flesh else 3, BOOT if flesh else BONE)
        if flesh:
            self.boot(ankle,toe)
            x,y = knee
            self.poly([(x-4,y-2),(x+4,y-2),(x+3,y+2),(x+1,y+1),
                       (x,y+4),(x-2,y+1),(x-4,y+3)], '#bd9b78')
            for t in (.35,.64):
                x = knee[0]+(ankle[0]-knee[0])*t
                y = knee[1]+(ankle[1]-knee[1])*t
                self.draw.line((x-3,y,x+3,y), fill=BOOT[0], width=2)
                self.draw.point((x+2,y), fill=GOLD[1])
        else:
            self.segment(ankle,toe,4,BONE)
            if self.actor == 'melee':
                start = tuple(a+(b-a)*.29 for a,b in zip(knee,ankle))
                end = tuple(a+(b-a)*.81 for a,b in zip(knee,ankle))
                self.segment(start,end,4,BOOT)
                self.draw.point(start,fill=GOLD[1])

    def cape(self, shoulder, hips):
        sx,sy = shoulder
        hx,hy = hips
        trailing = (-5-self.pose['lean']*.3)*self.fx
        hem = hy+23
        self.poly([(sx-13,sy+2),(sx-7,sy-5),(sx+7,sy-5),(sx+14,sy+2),
                   (hx+14+trailing,hem),(hx+9+trailing,hem-4),
                   (hx+6+trailing,hem+3),(hx+2+trailing,hem-4),
                   (hx-3+trailing,hem+5),(hx-7+trailing,hem-1),
                   (hx-10+trailing,hem+3),(hx-15+trailing,hem)], CLOTH[1])
        self.poly([(sx-8,sy+2),(hx-10+trailing,hem-1),(hx-5+trailing,hem-2),
                   (sx-2,sy+2)], CLOTH[2], None)
        self.poly([(sx+3,sy+2),(hx-1+trailing,hem),(hx+4+trailing,hem-4),
                   (sx+8,sy+3)], CLOTH[0], None)
        self.draw.line((sx-12,sy+1,sx-7,sy-2,sx+1,sy+1,sx+7,sy-2,sx+12,sy+1),
                       fill=CLOTH[2])

    def torso(self, shoulder, hips):
        sx, sy = shoulder
        hx, hy = hips
        w = (16 if self.actor == 'hero' else 10)*self.width
        if self.actor == 'hero':
            if self.back:
                self.poly([(sx-w,sy+1),(sx-w+4,sy-4),(sx+w-4,sy-4),(sx+w,sy+1),
                           (hx+8,hy-6),(hx+7,hy),(hx-8,hy),(hx-9,hy-5)], SKIN[1])
                self.poly([(sx-w+2,sy+2),(sx-2,sy-3),(sx+1,sy+2),
                           (sx+w-3,sy),(sx+w-5,sy+6),(sx-1,sy+6),(sx-6,sy+7)],
                          SKIN[2], None)
                self.poly([(sx-7,sy+3),(sx-1,sy+10),(hx,hy-4),(hx-4,hy-6)], SKIN[0], None)
                self.draw.line((sx+3,sy+5,hx+3,hy-7), fill=SKIN[2], width=2)
            else:
                left = sx-w+1+max(0,-self.fx)*3.2
                right = sx+w-1-max(0,self.fx)*3.2
                self.poly([(left+4,sy-4),(right-4,sy-4),(right-1,sy-2),
                           (right,sy+1),(right,sy+3),(right-1,sy+6),
                           ((right+hx+8)*.5,sy+9),(hx+8,hy-4),(hx+7,hy),
                           (hx-8,hy),(hx-9,hy-4),((left+hx-9)*.5,sy+9),
                           (left+1,sy+6),(left,sy+3),(left,sy+1),(left+1,sy-2)],SKIN[1])
                self.poly([(left+3,sy),(left+6,sy-2),(right-5,sy-2),(right-3,sy),
                           (right-3,sy+2),(right-6,sy+4),(left+6,sy+4),(left+3,sy+2)],
                          '#d49a72',None)
                self.draw.line((left+4,sy+5,sx-3,sy+6,sx+3,sy+6,right-4,sy+5),
                               fill='#a97454')
                self.poly([(sx+3,sy+8),(hx+7,hy-6),(hx+5,hy-2),(hx-1,hy-4)],
                          '#ad6f50',None)
                for y in (hy-10, hy-6):
                    self.draw.line((hx-4,y,hx+2,y-1), fill=SKIN[2])
                self.draw.line((sx-8,sy+2,sx-8,sy+5,sx-7,sy+7),fill='#825445')
                self.draw.line((sx-9,sy+4,sx-6,sy+5),fill='#a36f55')
        else:
            self.segment((sx,sy), (hx,hy-2), 4, BONE)
            for i in range(4):
                y = sy+3+i*3
                r = w-i
                self.draw.line([(round(sx-r),y-1),(sx,y+2),(round(sx+r),y-1)], fill=BONE[0], width=3)
                self.draw.line([(round(sx-r),y-2),(sx,y+1),(round(sx+r),y-2)], fill=BONE[2])
            self.draw.line((sx-8,sy,sx,sy+3,sx+8,sy),fill=BONE[2],width=2)
            if self.actor == 'melee':
                side = -1 if self.back else 1
                start = (sx+side*8*self.width,sy)
                end = (hx-side*6,hy-4)
                self.segment(start,end,3.8,BOOT)
                self.oval(sx+side*2,sy+7,2.7,2.7,GOLD[1])
            else:
                self.draw.line((sx-10,sy-2,sx-4,sy,sx,sy+4,sx+6,sy+1,sx+10,sy-1),
                               fill=CLOTH[0],width=3)
                self.oval(sx,sy+5,2.7,2.7,GOLD[1])
        fabric = BOOT if self.actor == 'hero' else CLOTH
        self.poly([(hx-9,hy-1),(hx+9,hy-1),(hx+12,hy+10),
                   (hx+5,hy+8),(hx,hy+12),(hx-5,hy+8),(hx-11,hy+10)], fabric[1])
        self.poly([(hx-6,hy+1),(hx-1,hy+1),(hx-3,hy+8),(hx-8,hy+8)], fabric[2], None)
        self.poly([(hx+1,hy+1),(hx+6,hy+2),(hx+9,hy+7),(hx+5,hy+6)], fabric[0], None)
        if self.actor == 'hero':
            self.draw.line((hx-10,hy+8,hx-6,hy+6,hx-1,hy+9,hx+5,hy+6,hx+10,hy+8),
                           fill='#b49975')
        else:
            for dx,dy in ((-8,6),(-4,8),(1,9),(5,7)):
                x,y = hx+dx,hy+dy
                self.poly([(x-2,y-4),(x+2,y-3),(x,y+2)],fabric[0],None)
        self.draw.line((hx-8,hy,hx+8,hy), fill=GOLD[0], width=3)
        if not self.back:
            self.draw.rectangle((hx-3,hy-2,hx+3,hy+2),outline=GOLD[2] if self.actor!='hero' else STEEL[1])
            self.draw.point((hx-1,hy),fill=GOLD[1])
        for dx in (-7,-5,5,7):
            self.draw.point((hx+dx,hy),fill=GOLD[2])

    def head(self, x, y):
        self.oval(x, y, 8, 9, SKIN[1] if self.actor == 'hero' else BONE[1])
        if self.actor == 'hero':
            pony_swing = math.sin(self.pose['frame']*math.tau/12)*self.fx if self.gait else 0
            pony = x-self.fx*(8+self.pose['lean']*.3)+pony_swing-2
            self.poly([(pony,y-7),(pony-4,y-3),(pony-3,y+6),(pony,y+10),
                       (pony+3,y+5),(pony+4,y-6)], BOOT[0])
            self.draw.line((pony-3,y-2,pony+2,y-2), fill=GOLD[1])
            self.poly([(x-8,y-1),(x-8,y-6),(x-4,y-10),(x+4,y-10),(x+8,y-5),
                       (x+7,y+4),(x-7,y+5)], BOOT[1])
            self.draw.line((x-5,y-7,x+1,y-8,x+5,y-6), fill=BOOT[2])
            self.draw.line((x-6,y-4,x-2,y-6,x+3,y-6), fill='#855f49')
            if not self.back:
                face = x+round(self.fx*3)
                self.poly([(face-5,y-3),(face+4,y-3),(face+5,y+2),
                           (face+3,y+6),(face-3,y+6),(face-5,y+3)], SKIN[1], None)
                nose = face+3*self.fx
                self.poly([(face-5,y+3),(face,y+4),(face+5,y+2),
                           (face+3,y+7),(face-1,y+9),(face-5,y+6)], BOOT[0])
                self.draw.line((face-4,y-2,face-2,y-3,face+3,y-2), fill=BOOT[0])
                self.draw.point((face+1+self.fx,y-1), fill='#efe1cc')
                self.draw.line((nose,y,nose+self.fx*2,y+2,nose,y+3), fill=SKIN[2])
                self.draw.line((face-1,y+6,face+2,y+6), fill='#93705b')
            return
        if self.actor == 'ranged':
            self.poly([(x-11,y+8),(x-10,y-6),(x-4,y-12),(x+4,y-12),
                       (x+10,y-5),(x+10,y+9),(x+5,y+10),(x-5,y+10)], CLOTH[1])
            self.draw.line((x-8,y-5,x-4,y-10,x+4,y-10), fill=CLOTH[2], width=2)
            if self.back:
                self.draw.line((x+3,y-7,x+4,y-1,x+3,y+6), fill=CLOTH[0], width=2)
                return
            self.oval(x,y+1,7,8,INK)
        if not self.back:
            eye = x+round(self.fx*3)
            self.poly([(eye-6,y-2),(eye-4,y-6),(eye+3,y-6),(eye+6,y-2),
                       (eye+4,y+4),(eye+3,y+8),(eye-4,y+8),(eye-5,y+4)], BONE[1])
            self.poly([(eye-5,y-3),(eye-3,y-5),(eye+2,y-5),(eye+3,y-3)], BONE[2], None)
            for offset in ((2,) if self.profile else (-3,3)):
                self.oval(eye+offset,y,2.15,2.15,INK,None)
                self.draw.point((eye+offset,y), fill='#d999ef')
            self.poly([(eye,y+1),(eye-1,y+4),(eye+1,y+4)],BONE[0],None)
            self.draw.line((eye-4,y+5,eye+4,y+5),fill=BONE[0])
            for dx in (-3,0,3):
                self.draw.line((eye+dx,y+5,eye+dx,y+7), fill=BONE[0])
        if self.actor == 'melee':
            self.poly([(x-2,y-9),(x-1,y-15),(x+3,y-15),(x+4,y-9)], GOLD[0])
            self.poly([(x-9,y-2),(x-8,y-7),(x-4,y-11),(x+3,y-12),
                       (x+8,y-7),(x+9,y-3),(x+3,y-3),(x-3,y-2)], GOLD[1])
            self.poly([(x-7,y-5),(x-4,y-9),(x,y-10),(x-1,y-4)], GOLD[2], None)
            self.draw.line((x-8,y-2,x+8,y-3), fill=GOLD[0], width=2)

    def arm(self, side):
        p = self.pose
        swing = self.foot_pose(side)[3] if self.gait else -p['stride']*side*.48
        shoulder_forward = p['lean']+swing*.13
        shoulder_up = 49-p['crouch']
        shoulder = self.point(side*13,shoulder_forward,shoulder_up)
        equipment = side == (1 if self.actor == 'hero' else -1)
        forward = swing
        lift = 0
        if equipment:
            if self.actor == 'hero':
                forward = p['shield_forward']+swing*.45
                lift = p['shield_up']+abs(swing)*.13
            else:
                forward = p['blade_forward']+swing*.5
                lift = p['blade_up']+abs(swing)*.13
        running = self.actor == 'hero' and p['lean']>=10 and self.gait is not None
        if running and not equipment:
            forward += 8
            lift = 7+max(0,swing)*.24
        elbow_setback = 7 if running else 3
        hand_forward = forward+p['lean']*.25
        hand_up = 26+lift-p['crouch']
        hand = self.point(side*14,hand_forward,hand_up)
        if equipment and self.actor == 'hero':
            # Solve the two arm segments in the plane of the shield's swing.
            # As the wrist reaches overhead, the bend falls naturally to near zero.
            dx,dy = hand_forward-shoulder_forward,hand_up-shoulder_up
            length = math.hypot(dx,dy)
            bend = math.sqrt(max(0,15.5**2-(length*.5)**2))/max(length,1)
            elbow = self.point(side*16,shoulder_forward+dx*.5+dy*bend,
                               shoulder_up+dy*.5-dx*bend)
        else:
            elbow = self.point(side*17,(forward+p['lean'])*.38-elbow_setback,
                               39+lift*.35-p['crouch'])
        flesh = self.actor == 'hero'
        colors = SKIN if flesh else CLOTH if self.actor == 'ranged' else BONE
        thickness = 9 if flesh else 6 if self.actor == 'ranged' else 3
        self.segment(shoulder, elbow, thickness, colors)
        self.segment(elbow, hand, thickness-1, colors)
        if flesh:
            self.oval(*shoulder,4.3,4.8,SKIN[1],None)
            self.draw.line((shoulder[0]-3,shoulder[1]-2,shoulder[0]-1,shoulder[1]-3,
                           shoulder[0]+2,shoulder[1]-2),fill=SKIN[2])
            band = tuple(a+(b-a)*.41 for a,b in zip(elbow,hand))
            self.segment(band,hand,thickness-2,BOOT)
            self.draw.line((band[0]-2,band[1],band[0]+2,band[1]), fill=GOLD[1])
            mid = tuple((a+b)*.5 for a,b in zip(band,hand))
            self.draw.line((mid[0]-1.8,mid[1],mid[0]+2,mid[1]),fill=BOOT[0],width=2)
            self.draw.point((mid[0]+1,mid[1]),fill=STEEL[2])
            self.oval(*hand,2.8,2.6,SKIN[1])
        if self.actor == 'melee' and side == 1:
            x, y = shoulder
            for dy in (4,2,0):
                self.oval(x,y+dy,7-dy//2,3,STEEL[1],GOLD[0])
            self.draw.line((x-5,y-1,x-2,y-2,x+2,y-2,x+5,y-1),fill=STEEL[2])
            for dx in (-4,4):
                self.draw.point((x+dx,y+3),fill=GOLD[2])
        if equipment:
            if flesh:
                self.shield(hand)
            else:
                self.weapon(hand)
        elif self.actor == 'ranged' and p['cast'] >= 2:
            x, y = hand
            self.poly([(x-4,y-5),(x,y-9),(x+4,y-5),(x,y-1)], '#e6b5fa', '#9d55d6')

    def shield(self, center):
        self.shield_anchor = [round(value * SCALE) for value in center]
        x, y = center
        # Side-facing while relaxed. Turn the face toward the attack when raised.
        aim = min(1, max(0, (self.pose['shield_forward']-6)/11))
        normal = -self.fx*(1-aim)+self.fy*aim
        w = 6+8*abs(normal)
        brush = self.draw
        if self.pose['shield_pitch_deg']:
            angle = self.pose['shield_pitch_deg']
            pitch = math.radians(angle)
            sine,cosine = math.sin(pitch),math.cos(pitch)
            forward_x = self.fx*aim+self.fy*(1-aim)
            length = math.hypot(forward_x,normal)
            fx,fy = forward_x/length,normal/length
            # Pitch the disc locally about its horizontal crossbar, then project.
            down = (fx*sine,cosine+.43*fy*sine)
            facing = 1 if fy>=0 else -1
            blend = min(1,angle/35)
            across = (w/14*(1-blend)+abs(fy)*blend,-.43*fx*facing*blend)
            brush = ShieldBrush(self.draw,center,across,down)
            normal = fy*cosine+.43*sine
            w = 14
        def oval(cx,cy,rx,ry,fill,outline=INK):
            brush.ellipse((cx-rx,cy-ry,cx+rx,cy+ry),fill=fill,outline=outline)
        oval(x+1,y+1,w+2,15,GOLD[0])
        oval(x,y,w+1.5,15,GOLD[1])
        oval(x,y-1,w+.6,13.8,GOLD[1],None)
        wood = normal < -.15
        oval(x,y,w-1,12,'#775037' if wood else '#383742')
        if wood:
            for part in (-.45,0,.45):
                board_x = x+w*part
                brush.line((board_x,y-9,board_x,y+8),fill='#593b30')
        else:
            for index in range(10):
                angle = index*math.tau/10+math.pi/10
                rx,ry = x+math.cos(angle)*(w-2.5),y+math.sin(angle)*9.7
                brush.line((rx-.55,ry+.7,rx,ry-.6,rx+.75,ry+.25),fill=GOLD[1])
            for dx,dy in ((-.38,-5),(.37,3),(.56,-5),(-.62,4),(.31,7)):
                brush.line((x+w*dx,y+dy,x+w*dx+1.1,y+dy-.7),fill='#5c514a')
        brush.line((x,y-11,x,y+11),fill=GOLD[0],width=3)
        brush.line((x-.65,y-11,x-.65,y+10),fill=GOLD[1])
        brush.line((x-w+2,y,x+w-2,y),fill=GOLD[0],width=3)
        brush.line((x-w+2,y-1,x+w-2,y-1),fill=GOLD[1])
        if not wood:
            oval(x,y,3.8,3.8,GOLD[1])
            brush.polygon([(x,y-3),(x+2.4,y-1),(x+2,y+2),(x,y+3),(x-2.2,y+1.3),(x-2,y-1.5)],
                          fill='#55c6b3',outline=INK)
            brush.line((x-1.5,y+.4,x-1,y-1.35,x+.3,y-1.8),fill='#c9fff2')
        for dx,dy in ((-.76,-7),(.76,-7),(-.76,7),(.76,7)):
            brush.point((x+w*dx,y+dy),fill=GOLD[2])
        for index in range(12):
            angle = index*math.tau/12
            rx,ry = x+math.cos(angle)*w,y+math.sin(angle)*13.2
            brush.point((rx,ry),fill=GOLD[0])
            if index not in (1,2,3):
                brush.point((rx-.55,ry-.55),fill=GOLD[2])

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
            self.poly([(x-7,y-1),(x-5,y+5),(x,y+9),(x+6,y+3),(x+7,y-1),
                       (x+4,y+1),(x,y+6),(x-4,y+2)], GOLD[1])
            self.poly([(x,y-8),(x+5,y-3),(x+4,y+4),(x,y+7),(x-5,y)], '#9951c2')
            self.poly([(x,y-7),(x+1,y+2),(x-4,y),(x-3,y-4)], '#efb8fc', None)
            self.poly([(x+1,y+2),(x+4,y-3),(x+4,y+3),(x,y+6)], '#713a9c', None)
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
        shoulder = self.point(0,p['lean'],50-p['crouch'])
        hips = self.point(0,p['lean']*.25,29-p['crouch'])
        if self.actor == 'ranged' and not self.back:
            self.cape(shoulder,hips)
        for side in (-self.near,self.near):
            self.leg(side)
        self.arm(-self.near)
        if self.actor == 'ranged' and self.back:
            self.cape(shoulder,hips)
        else:
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
            emitters = []
            for direction in range(len(DATA['directions'])):
                anchors = []
                for i, pose in enumerate(frames):
                    figure = Figure(actor,direction,pose,DATA['gaits'].get(name))
                    canvas = figure.render()
                    bbox = canvas.getbbox()
                    assert bbox and 0 < bbox[0] < bbox[2] < CELL and 0 < bbox[1] < bbox[3] < CELL, (
                        actor, name, direction, i, bbox
                    )
                    sheet.paste(canvas, (CELL*i,CELL*direction))
                    if actor == 'hero' and name in ('guard','guard_walk'):
                        anchors.append(figure.shield_anchor)
                if anchors:
                    emitters.append(anchors)
            path = f'{actor}-{name}.png'
            sheet.save(OUT/path, optimize=True)
            row = {
                'actor': actor, 'action': name, 'file': path, 'frames': len(frames),
                'loop': clip['loop'],
            }
            if emitters:
                row['shield_px'] = emitters
            manifest['clips'].append(row)
    (OUT/'atlas.json').write_text(json.dumps(manifest,indent=2)+'\n', encoding='utf-8')
    print(f"Exported {len(manifest['clips'])} sheets in {len(DATA['directions'])} directions.")


if __name__ == '__main__':
    build()
