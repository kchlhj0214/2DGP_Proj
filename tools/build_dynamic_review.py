"""Small, readable 3D action poses for subsequent pixel conversion; no runtime changes."""
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Matrix

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_motion_review as previous
base=previous.base
DATA=json.loads((ROOT/'data/art_dynamic.json').read_text(encoding='utf-8'))
OUT=ROOT/'art/model-review-v3'
OUT.mkdir(parents=True,exist_ok=True)


def body(point,row,reference=None):
    """Keep soles planted while compressing the stance and counter-turning the torso."""
    p=point.copy()
    height=point.z if reference is None else reference.z
    weight=previous.smooth(.10,.95,height)
    p.z-=row['crouch_m']*weight
    p.x+=row['shift_m'][0]*weight
    p.y+=row['shift_m'][1]*weight
    pivot=Vector((0,0,.95-row['crouch_m']))
    twist=Matrix.Rotation(math.radians(row['twist_deg']),3,'Z')
    p=p.lerp(pivot+twist@(p-pivot),previous.smooth(.8,1.3,height))
    return p


def animate(root,rows,deform,weapons=()):
    bpy.context.view_layer.update()
    for obj in list(root.children_recursive):
        if obj.type!='MESH':continue
        bpy.context.view_layer.objects.active=obj
        for mod in list(obj.modifiers):bpy.ops.object.modifier_apply(modifier=mod.name)
        matrix=obj.matrix_world.copy();inverse=matrix.inverted()
        points=[matrix@v.co for v in obj.data.vertices]
        basis=obj.shape_key_add(name='Basis')
        for v,p in zip(basis.data,points):v.co=inverse@deform(p,rows[0],obj in weapons)
        for row in rows[1:]:
            key=obj.shape_key_add(name=row['id'])
            for v,p in zip(key.data,points):v.co=inverse@deform(p,row,obj in weapons)
            for pose in rows:
                key.value=float(row['id']==pose['id'])
                key.keyframe_insert('value',frame=pose['frame'])
        # Linear pose-to-pose transitions: 1-frame strikes and explicit held impact poses.
        anim=obj.data.shape_keys.animation_data
        if anim and anim.action:
            for layer in anim.action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for curve in bag.fcurves:
                            for key in curve.keyframe_points:key.interpolation='LINEAR'


def hero():
    root=bpy.data.objects.new('Hero dynamic review',None)
    bpy.context.scene.collection.objects.link(root);base.GROUP=root
    shields=[];original=base.make_shield
    def capture():
        before=set(bpy.data.objects);original()
        shields.extend(set(bpy.data.objects)-before)
    base.make_shield=capture
    try:base.make_hero()
    finally:base.make_shield=original
    def deform(p,row,shield):
        reference=previous.deformed(previous.WRIST,row,True) if shield else None
        return body(previous.deformed(p,row,shield),row,reference)
    animate(root,DATA['hero_poses'],deform,shields)
    return root


def melee():
    root=bpy.data.objects.new('Melee knight sword review',None)
    bpy.context.scene.collection.objects.link(root);base.GROUP=root
    base.make_skeleton('melee')
    for obj in list(root.children_recursive):
        if obj.name.startswith(('Sword hilt','Sword crossguard','Steel sword blade')):
            bpy.data.objects.remove(obj,do_unlink=True)
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ROOT/DATA['sword']['file']))
    imported=set(bpy.data.objects)-before
    grip=Vector(DATA['sword']['hand_grip_m'])
    rotation=Vector((0,0,-1)).rotation_difference(Vector(DATA['sword']['direction']).normalized())
    bpy.context.view_layer.update()
    weapons=[]
    for obj in imported:
        if obj.type!='MESH':continue
        points=[obj.matrix_world@v.co for v in obj.data.vertices]
        obj.parent=root;obj.matrix_world=Matrix.Identity(4)
        for v,p in zip(obj.data.vertices,points):
            v.co=grip+rotation@((p-Vector(DATA['sword']['source_grip_m']))*DATA['sword']['scale'])
        obj.name='Polyfork arming sword';weapons.append(obj)
    for obj in imported:
        if obj.type=='EMPTY':bpy.data.objects.remove(obj,do_unlink=True)
    shoulder=Vector((-.225,0,1.42))
    def deform(p,row,weapon):
        turn=Matrix.Rotation(math.radians(row['arm_yaw_deg']),3,'Z')
        lift=Matrix.Rotation(math.radians(row['arm_lift_deg']),3,'X')
        q=shoulder+turn@lift@(p-shoulder)
        arm=1 if weapon else (1-previous.smooth(-.30,-.19,p.x))*(1-previous.smooth(1.41,1.53,p.z))*previous.smooth(.83,.94,p.z)
        p=p.lerp(q,arm)
        pivot=Vector((0,0,.95))
        lean=Matrix.Rotation(math.radians(row['lean_deg']),3,'X')
        hand=shoulder+turn@lift@(grip-shoulder)
        amount=previous.smooth(.85,1.2,hand.z if weapon else p.z)
        p=p.lerp(pivot+lean@(p-pivot),amount)
        hand=hand.lerp(pivot+lean@(hand-pivot),amount)
        return body(p,row,hand if weapon else None)
    animate(root,DATA['melee_poses'],deform,weapons)
    return root


def validate():
    def filled(value):
        assert value is not None and value!=''
        if isinstance(value,dict):
            for v in value.values():filled(v)
        elif isinstance(value,list):
            assert value
            for v in value:filled(v)
    filled(DATA);base.validate()
    for rows in (DATA['hero_poses'],DATA['melee_poses']):
        assert len({r['id'] for r in rows})==len(rows)
        assert all(a['frame']<b['frame'] for a,b in zip(rows,rows[1:]))
    for row in DATA['hero_poses']:previous.arm_pose(Vector(row['wrist_m']))
    for clip in DATA['clips']:
        assert clip['actor'] in ('hero','melee')
        rows=DATA[clip['actor']+'_poses']
        assert rows[0]['frame']<=clip['start']<clip['end']<=rows[-1]['frame']
    assert (ROOT/DATA['sword']['file']).is_file()


def main():
    validate()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for row in base.DATA['palette']:base.material(row)
    actors={'hero':hero(),'melee':melee()};base.GROUP=None;base.setup_scene()
    scene=bpy.context.scene;scene.render.fps=24;scene.frame_end=60
    settings=dict(base.DATA['render'][0],resolution_px=400,samples=12,orthographic_scale_m=2.9)
    for name,actor in actors.items():
        for other,root in actors.items():previous.visible(root,other==name)
        scene.frame_set(1)
        for angle in (0,30,90,180):base.render_view(actor,angle,settings,OUT/f'{name}-idle-{angle}.png')
    for clip in DATA['clips']:
        for name,root in actors.items():previous.visible(root,name==clip['actor'])
        for frame in range(clip['start'],clip['end']+1):
            scene.frame_set(frame)
            base.render_view(actors[clip['actor']],30,settings,OUT/f'{clip["id"]}-{frame:02}.png')
        scene.timeline_markers.new(clip['id'],frame=clip['start'])
    for root in actors.values():previous.visible(root,True)
    actors['hero'].location.x=-.8;actors['melee'].location.x=.8;scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shield-attack-dynamic-review.blend'))
    (OUT/'manifest.json').write_text(json.dumps(DATA,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DYNAMIC_REVIEW_COMPLETE')


if __name__=='__main__':main()
