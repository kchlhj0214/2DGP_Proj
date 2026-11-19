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


def gif(name, frames, durations=None):
    # GIF delays have 10ms precision. Alternate 60/70ms to average 16fps.
    if durations is None:
        durations = [70 if i%4 == 3 else 60 for i in range(len(frames))]
    frames[0].save(OUT/name, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0)


def pose_board():
    entries = [
        ('hero','parry','W',3,'패링 · 무릎을 굽혀 힘 모으기'),
        ('hero','parry','SW',7,'패링 · 팔을 머리 위로 뻗어 막기'),
        ('hero','guard','SE',3,'기본 방어 · 방패 유지'),
        ('melee','chop','E',6,'근접 공격 · 머리 위로 들어 올리기'),
        ('melee','chop','E',8,'근접 공격 · 찍어 내리기'),
        ('ranged','cast','SE',0,'원거리 공격 · 지팡이 발사'),
    ]
    board = Image.new('RGB', (1158,806), BG)
    draw = ImageDraw.Draw(board)
    draw.text((30,18),'SHIELD ATTACK',font=font(29),fill=ACCENT)
    draw.text((275,25),'전투 자세',font=font(20),fill=TEXT)
    for i, (actor,action,direction,frame,label) in enumerate(entries):
        x = 18 + (i%3)*376
        y = 74 + (i//3)*362
        draw.rectangle((x,y,x+363,y+346), fill=PANEL)
        draw.line((x+28,y+304,x+336,y+304), fill='#4c4048')
        stamp(board,read_frames(actor,action,direction)[frame],(x+180,y+300),2)
        draw.text((x+16,y+321),label,font=font(17),fill=TEXT)
    board.save(OUT/'motion-board.png')


def parry_scene():
    chop = read_frames('melee','chop','E')
    bounce = read_frames('melee','deflected','E')
    parry = read_frames('hero','parry','W')
    guard = read_frames('hero','guard','W')
    frames = []
    for i in range(26):
        canvas = Image.new('RGB',(830,440),BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((26,17),'내려치기 → 올려막기 → 칼 반동과 뒷걸음질',font=font(23),fill=TEXT)
        draw.line((62,357,768,357), fill='#4c4048', width=2)
        # Impact occurs on frame 8; the same contact pose opens the recoil clip.
        enemy = chop[i] if i<8 else bounce[min(i-8,len(bounce)-1)]
        hero = parry[max(0,i-3)] if i<3+len(parry) else guard[i%len(guard)]
        stamp(canvas,enemy,(302,355),2)
        stamp(canvas,hero,(527,355),2)
        if i in (8,9):
            x,y = 449,165
            draw.line((x-20,y+10,x+21,y-9),fill='#fff1b8',width=4)
            draw.line((x-9,y-16,x+9,y+14),fill='#f5c375',width=3)
        draw.text((247,390),'근접 해골',font=font(18),fill=ACCENT)
        draw.text((494,390),'방패 전사',font=font(18),fill=ACCENT)
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


def guard_walk_scene():
    side = read_frames('hero','guard_walk','W')
    diagonal = read_frames('hero','guard_walk','SE')
    frames = []
    for index in range(24):
        canvas = Image.new('RGB',(1020,386),BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((26,18),'기본 방어 상태로 걷기',font=font(24),fill=TEXT)
        for panel,(title,clip,anchor,step) in enumerate((
            ('측면',side,(397,320),(-8,0)),
            ('앞 사선',diagonal,(633,277),(7,2)),
        )):
            left = 18+panel*500
            draw.rectangle((left,65,left+483,367),fill=PANEL)
            draw.text((left+16,79),title,font=font(17),fill=ACCENT)
            x,y = anchor
            dx,dy = step
            for mark in range(-4,31,4):
                mx,my = x+dx*mark,y+dy*mark+7
                if left+14 < mx < left+469:
                    draw.line((mx-4,my,mx+7,my+2*dy),fill='#51434a',width=2)
            px,py = x+dx*index,y+dy*index
            draw.ellipse((px-37,py-1,px+37,py+8),fill='#1c1924')
            stamp(canvas,clip[index%len(clip)],(px,py),2)
        frames.append(canvas)
    gif('guard-walk.gif',frames)


def hero_parry_detail():
    views = [read_frames('hero','parry',direction) for direction in ('W','SW')]
    frames = []
    durations = []
    for index,(side,diagonal) in enumerate(zip(*views)):
        canvas = Image.new('RGB',(880,482),BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((24,17),'방패 전사 · 수정된 패링',font=font(24),fill=TEXT)
        for x,label,sprite in ((224,'측면',side),(656,'앞 사선',diagonal)):
            draw.rectangle((x-206,66,x+206,439),fill=PANEL)
            draw.text((x-188,80),label,font=font(17),fill=ACCENT)
            draw.line((x-161,405,x+161,405),fill='#4c4048')
            stamp(canvas,sprite,(x,401),2)
        if 6 <= index <= 8:
            label = '머리 위 · 방패 면을 정면에서 위로 45도'
        elif index < 4:
            label = '방패를 낮추고 힘 모으기'
        elif index < 6:
            label = '방패를 밀어 올리며 기울이기'
        else:
            label = '기본 방어 자세로 복귀'
        draw.text((440,460),label,font=font(18),fill=TEXT,anchor='mm')
        frames.append(canvas)
        durations.append(420 if index == 7 else 240 if index == 15 else 80)
    gif('hero-parry-diagonal-review.gif',frames,durations)


if __name__ == '__main__':
    pose_board()
    parry_scene()
    movement_scene()
    directions_board()
    guard_walk_scene()
    hero_parry_detail()
