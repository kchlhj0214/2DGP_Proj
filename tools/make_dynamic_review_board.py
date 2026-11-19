"""Contact sheet and synchronized previews, including 36px-tall pixel readability."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'art/model-review-v3'
DATA=json.loads((ROOT/'data/art_dynamic.json').read_text(encoding='utf-8'))
BG=(25,29,36)
def font(size):return ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',size)


def picture(name):
    im=Image.open(OUT/name).convert('RGBA')
    bbox=im.getchannel('A').getbbox()
    assert bbox and 0<bbox[0]<bbox[2]<im.width and 0<bbox[1]<bbox[3]<im.height,name
    bg=Image.new('RGB',im.size,BG);bg.paste(im,(0,0),im)
    return bg


def main():
    for path in OUT.glob('*.png'):
        if path.name!='review-board.png':picture(path.name)
    entries=[('melee-idle-0.png','기사검 · 정면'),('melee-idle-90.png','기사검 · 측면'),
             ('parry-05.png','패링 · 낮게 준비'),('parry-07.png','패링 · 순간 올려치기'),
             ('parry-12.png','패링 · 큰 후속 동작'),('hero-hit-35.png','피격 · 상체 반동'),
             ('slash-08.png','베기 · 몸을 틀어 준비'),('slash-12.png','베기 · 빠른 쓸어 베기')]
    board=Image.new('RGB',(1200,700),BG);draw=ImageDraw.Draw(board)
    draw.text((22,14),'SHIELD ATTACK · 기사검 / 과장된 액션 검토',font=font(26),fill='white')
    for i,(name,label) in enumerate(entries):
        x=i%4*300;y=55+i//4*320
        board.paste(picture(name).resize((280,280)),(x+10,y))
        draw.text((x+16,y+280),label,font=font(18),fill='white')
    board.save(OUT/'review-board.png')
    clips=[]
    for clip in DATA['clips']:
        frames=[picture(f'{clip["id"]}-{n:02}.png') for n in range(clip['start'],clip['end']+1)]
        frames[0].save(OUT/f'{clip["id"]}.gif',save_all=True,append_images=frames[1:],
                       duration=[42]*(len(frames)-1)+[350],loop=0,disposal=2)
        clips.append(frames)
    combined=[]
    for n in range(max(map(len,clips))+8):
        canvas=Image.new('RGB',(1000,690),BG);draw=ImageDraw.Draw(canvas)
        draw.text((20,12),'3D 동작 / 작은 도트 가독성 비교 (약 36px 키 → 3배 확대)',font=font(22),fill='white')
        for i,(clip,frames) in enumerate(zip(DATA['clips'],clips)):
            x=i%2*500;y=55+i//2*315
            source=frames[min(n,len(frames)-1)]
            canvas.paste(source.resize((290,290)),(x,y))
            small=source.resize((58,58),Image.Resampling.NEAREST).resize((174,174),Image.Resampling.NEAREST)
            canvas.paste(small,(x+300,y+70))
            draw.text((x+12,y+286),clip['label'],font=font(16),fill=(230,224,211))
        combined.append(canvas)
    combined[0].save(OUT/'motion-comparison.gif',save_all=True,append_images=combined[1:],duration=42,loop=0,disposal=2)
    print('Verified all frames: visible, no clipping; created four clips and pixel comparison.')


if __name__=='__main__':main()
