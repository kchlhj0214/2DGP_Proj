"""Compose actual 3D review frames into a board and looping preview."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'art/model-review-v2'
DATA=json.loads((ROOT/'data/art_motion.json').read_text(encoding='utf-8'))
BG=(26,30,36)
font=lambda n:ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',n)


def composite(name):
    source=Image.open(OUT/name).convert('RGBA')
    bbox=source.getchannel('A').getbbox()
    assert bbox and bbox[0]>0 and bbox[1]>0 and bbox[2]<source.width and bbox[3]<source.height,name
    result=Image.new('RGB',source.size,BG)
    result.paste(source,(0,0),source)
    return result


def main():
    entries=[('hero-idle-0.png','기본 · 정면'),('hero-idle-90.png','기본 · 왼쪽 측면'),
        ('melee-ready-30.png','근접 적 · 칼끝 앞·위'),('melee-ready-90.png','근접 적 · 측면'),
        ('hero-ready.png','패링 ① 준비'),('hero-draw_forward.png','② 왼팔을 앞으로'),
        ('hero-upstroke.png','③ 수그리며 올려치기'),('hero-follow_through.png','④ 올려친 뒤 회수')]
    board=Image.new('RGB',(1440,890),BG)
    draw=ImageDraw.Draw(board)
    draw.text((26,18),'SHIELD ATTACK · 방패 방향 / 패링 동작 / 칼 준비 자세',font=font(28),fill=(235,226,210))
    for i,(filename,label) in enumerate(entries):
        x=i%4*360;y=70+i//4*405
        pic=composite(filename).resize((360,360),Image.Resampling.LANCZOS)
        board.paste(pic,(x,y))
        draw.text((x+16,y+362),label,font=font(20),fill=(225,225,225))
    board.save(OUT/'pose-and-motion-review.png')
    frames=[]
    for n in range(1,26):
        pic=composite(f'parry-{n:02}.png')
        draw=ImageDraw.Draw(pic)
        draw.text((16,14),'패링 동작 · 3D 검토',font=font(20),fill=(235,226,210))
        frames.append(pic)
    frames[0].save(OUT/'parry-motion.gif',save_all=True,append_images=frames[1:],
                   duration=[500]+[42]*23+[500],loop=0,disposal=2)
    # All requested action frames, plus idle and sword views, must be present and non-clipped.
    for path in OUT.glob('*.png'):
        if path.name!='pose-and-motion-review.png':composite(path.name)
    print('Validated review images and 25 motion frames; board and GIF saved.')


if __name__=='__main__':main()
