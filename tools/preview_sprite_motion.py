"""Compose review images using the same exported sprites available to the game."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parents[1] / 'art/sprite-review'
ATLAS = json.loads((OUT / 'atlas.json').read_text(encoding='utf-8'))
CELL = ATLAS['cell_px']
OX, OY = ATLAS['origin_px']
CLIPS = {(row['actor'], row['action']): row for row in ATLAS['clips']}
BG = '#191821'
PANEL = '#252331'
TEXT = '#eee3d2'
ACCENT = '#d9ad74'


def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', size)


def read_frames(actor, action, direction):
    row = CLIPS[actor, action]
    index = ATLAS['directions'].index(direction)
    with Image.open(OUT / row['file']) as sheet:
        return [sheet.crop((i*CELL,index*CELL,(i+1)*CELL,(index+1)*CELL))
                for i in range(row['frames'])]


def stamp(canvas, sprite, anchor, zoom=1):
    x, y = anchor
    sprite = sprite.resize((CELL*zoom, CELL*zoom), Image.Resampling.NEAREST)
    canvas.paste(sprite, (x-OX*zoom,y-OY*zoom), sprite)


def gif(name, frames):
    # GIF delays have 10ms precision. Alternate 60/70ms to average 16fps.
    frames[0].save(OUT/name, save_all=True, append_images=frames[1:],
                   duration=[70 if i%4 == 3 else 60 for i in range(len(frames))], loop=0)


def pose_board():
    entries = [
        ('hero','parry','W',3,'패링 · 무릎을 굽혀 힘 모으기'),
        ('hero','parry','W',7,'패링 · 다리를 펴며 올려막기'),
        ('hero','guard','SE',3,'기본 방어 · 방패 유지'),
        ('melee','chop','E',6,'근접 공격 · 머리 위로 들어 올리기'),
        ('melee','chop','E',8,'근접 공격 · 찍어 내리기'),
        ('ranged','cast','SE',0,'원거리 공격 · 지팡이 발사'),
    ]
    board = Image.new('RGB', (960,600), BG)
    draw = ImageDraw.Draw(board)
    draw.text((30,18),'SHIELD ATTACK',font=font(29),fill=ACCENT)
    draw.text((275,25),'2D 도트 모션',font=font(20),fill=TEXT)
    for i, (actor,action,direction,frame,label) in enumerate(entries):
        x = 18 + (i%3)*312
        y = 74 + (i//3)*258
        draw.rectangle((x,y,x+299,y+241), fill=PANEL)
        draw.line((x+40,y+198,x+260,y+198), fill='#4c4048')
        stamp(board,read_frames(actor,action,direction)[frame],(x+150,y+193),2)
        draw.text((x+13,y+218),label,font=font(15),fill=TEXT)
    board.save(OUT/'motion-board.png')


def parry_scene():
    chop = read_frames('melee','chop','E')
    bounce = read_frames('melee','deflected','E')
    parry = read_frames('hero','parry','W')
    guard = read_frames('hero','guard','W')
    frames = []
    for i in range(26):
        canvas = Image.new('RGB',(600,320),BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((26,17),'내려치기 → 올려막기 → 칼 반동과 뒷걸음질',font=font(21),fill=TEXT)
        draw.line((40,247,560,247), fill='#4c4048', width=2)
        # Impact occurs on frame 8; the same contact pose opens the recoil clip.
        enemy = chop[i] if i<8 else bounce[min(i-8,len(bounce)-1)]
        hero = parry[max(0,i-3)] if i<3+len(parry) else guard[i%len(guard)]
        stamp(canvas,enemy,(228,245),2)
        stamp(canvas,hero,(378,245),2)
        if i in (8,9):
            x,y = 327,162
            draw.line((x-13,y+7,x+14,y-6),fill='#fff1b8',width=3)
            draw.line((x-6,y-11,x+6,y+9),fill='#f5c375',width=2)
        draw.text((26,275),'근접 해골',font=font(15),fill=ACCENT)
        draw.text((442,275),'방패 전사',font=font(15),fill=ACCENT)
        frames.append(canvas)
    gif('parry-and-recoil.gif',frames+[frames[-1]]*5)


def movement_scene():
    canvas_size = (780,466)
    actors = ('hero','melee','ranged')
    names = ('방패 전사','근접 해골','원거리 해골')
    frames = []
    clips = {(actor,action):read_frames(actor,action,'SE') for actor in actors
             for action in ('walk','run')}
    casts = read_frames('ranged','cast','W')
    chops = read_frames('melee','chop','W')
    guard = read_frames('hero','guard','SE')
    for tick in range(24):
        canvas = Image.new('RGB',canvas_size,BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((24,15),'걷기 · 달리기 · 기본 방어와 공격',font=font(21),fill=TEXT)
        for i,actor in enumerate(actors):
            x=148+i*252
            draw.text((x-37,57),names[i],font=font(17),fill=ACCENT)
            for row,action in enumerate(('walk','run')):
                y=190+row*123
                draw.line((x-60,y+2,x+78,y+2),fill='#4c4048')
                clip = clips[actor,action]
                stamp(canvas,clip[tick%len(clip)],(x,y))
                draw.text((x-16,y+8),{'walk':'걷기','run':'달리기'}[action],font=font(14),fill=TEXT)
            action = (guard,chops,casts)[i]
            stamp(canvas,action[tick%len(action) if i==0 else min(tick,len(action)-1)],(x,427))
            if i==2 and tick<12:
                orb_x=x-53-tick*7
                draw.ellipse((orb_x-4,363,orb_x+4,371),fill='#9e57d0')
                draw.ellipse((orb_x-2,364,orb_x+2,368),fill='#eab1ff')
            draw.text((x-30,434),('기본 방어','내려치기','지팡이 발사')[i],font=font(14),fill=TEXT)
        frames.append(canvas)
    gif('movement-and-attacks.gif',frames)


def directions_board():
    board = Image.new('RGB',(900,468),BG)
    draw = ImageDraw.Draw(board)
    draw.text((22,13),'8방향 기본 자세',font=font(21),fill=TEXT)
    for row,actor in enumerate(('hero','melee','ranged')):
        for col,direction in enumerate(ATLAS['directions']):
            x,y = 63+col*110,160+row*135
            stamp(board,read_frames(actor,'idle',direction)[0],(x,y))
            draw.text((x-8,y+12),direction,font=font(15),fill=ACCENT)
    board.save(OUT/'directions.png')


if __name__ == '__main__':
    pose_board()
    parry_scene()
    movement_scene()
    directions_board()
