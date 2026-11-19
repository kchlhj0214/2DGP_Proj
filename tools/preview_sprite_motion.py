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
    board = Image.new('RGB', (1158,722), BG)
    draw = ImageDraw.Draw(board)
    draw.text((30,18),'SHIELD ATTACK',font=font(29),fill=ACCENT)
    draw.text((275,25),'전투 자세',font=font(20),fill=TEXT)
    for i, (actor,action,direction,frame,label) in enumerate(entries):
        x = 18 + (i%3)*376
        y = 74 + (i//3)*316
        draw.rectangle((x,y,x+363,y+301), fill=PANEL)
        draw.line((x+28,y+255,x+336,y+255), fill='#4c4048')
        stamp(board,read_frames(actor,action,direction)[frame],(x+180,y+251),2)
        draw.text((x+16,y+274),label,font=font(17),fill=TEXT)
    board.save(OUT/'motion-board.png')


def parry_scene():
    chop = read_frames('melee','chop','E')
    bounce = read_frames('melee','deflected','E')
    parry = read_frames('hero','parry','W')
    guard = read_frames('hero','guard','W')
    frames = []
    for i in range(26):
        canvas = Image.new('RGB',(830,420),BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((26,17),'내려치기 → 올려막기 → 칼 반동과 뒷걸음질',font=font(23),fill=TEXT)
        draw.line((62,337,768,337), fill='#4c4048', width=2)
        # Impact occurs on frame 8; the same contact pose opens the recoil clip.
        enemy = chop[i] if i<8 else bounce[min(i-8,len(bounce)-1)]
        hero = parry[max(0,i-3)] if i<3+len(parry) else guard[i%len(guard)]
        stamp(canvas,enemy,(302,335),2)
        stamp(canvas,hero,(527,335),2)
        if i in (8,9):
            x,y = 450,210
            draw.line((x-20,y+10,x+21,y-9),fill='#fff1b8',width=4)
            draw.line((x-9,y-16,x+9,y+14),fill='#f5c375',width=3)
        draw.text((247,370),'근접 해골',font=font(18),fill=ACCENT)
        draw.text((494,370),'방패 전사',font=font(18),fill=ACCENT)
        frames.append(canvas)
    gif('parry-and-recoil.gif',frames+[frames[-1]]*5)


def movement_scene():
    columns = [
        ('방패 전사',('hero','guard_walk','SE','방패를 든 채 걷기'),
         ('hero','run','E','달리기')),
        ('근접 해골',('melee','walk','SE','걷기'),
         ('melee','chop','W','내려치기')),
        ('원거리 해골',('ranged','walk','SE','걷기'),
         ('ranged','cast','W','지팡이 발사')),
    ]
    clips = {(actor,action):read_frames(actor,action,direction)
             for _,top,bottom in columns for actor,action,direction,_ in (top,bottom)}
    frames = []
    for tick in range(24):
        canvas = Image.new('RGB',(1140,724),BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((24,16),'캐릭터 이동과 공격',font=font(24),fill=TEXT)
        for i,(name,top,bottom) in enumerate(columns):
            x=190+i*380
            draw.text((x,75),name,font=font(19),fill=ACCENT,anchor='mm')
            for y,(actor,action,_,label) in zip((318,679),(top,bottom)):
                height = 226 if y == 318 else 279
                draw.rectangle((x-175,y-height,x+175,y+32),fill=PANEL)
                draw.line((x-145,y+2,x+145,y+2),fill='#4c4048')
                clip = clips[actor,action]
                loop = CLIPS[actor,action]['loop']
                frame = tick%len(clip) if loop else min(tick,len(clip)-1)
                stamp(canvas,clip[frame],(x,y),2)
                if action == 'cast' and tick<7:
                    orb_x = x-144-tick*14
                    if orb_x > x-175:
                        draw.ellipse((orb_x-8,y-183,orb_x+8,y-167),fill='#9e57d0')
                        draw.ellipse((orb_x-3,y-180,orb_x+3,y-172),fill='#eab1ff')
                draw.text((x,y+17),label,font=font(17),fill=TEXT,anchor='mm')
        frames.append(canvas)
    gif('movement-and-attacks.gif',frames)


def directions_board():
    board = Image.new('RGB',(1050,540),BG)
    draw = ImageDraw.Draw(board)
    draw.text((22,13),'8방향 기본 자세',font=font(21),fill=TEXT)
    for row,actor in enumerate(('hero','melee','ranged')):
        for col,direction in enumerate(ATLAS['directions']):
            x,y = 65+col*131,163+row*171
            stamp(board,read_frames(actor,'idle',direction)[0],(x,y))
            draw.text((x-8,y+12),direction,font=font(15),fill=ACCENT)
    board.save(OUT/'directions.png')


if __name__ == '__main__':
    pose_board()
    parry_scene()
    movement_scene()
    directions_board()
