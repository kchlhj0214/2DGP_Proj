"""Actual 3D pose/motion review, with rest meshes preserved in v1.

Uses continuous vertex deformations and shape-key animation for this review.
Does not modify gameplay timing or export final pixel animation.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector, Matrix

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_art_models as base

DATA=json.loads((ROOT/'data/art_motion.json').read_text(encoding='utf-8'))
OUT=ROOT/'art/model-review-v2'
OUT.mkdir(parents=True,exist_ok=True)
SHOULDER=Vector((.30,.01,1.39))
ELBOW=Vector((.405,-.015,1.15))
WRIST=Vector((.405,-.23,1.045))
PIVOT=Vector(DATA['hero']['body_pivot_m'])


def smooth(a,b,x):
    t=max(0,min(1,(x-a)/(b-a)))
    return t*t*(3-2*t)


def arm_pose(wrist):
    l1=(ELBOW-SHOULDER).length;l2=(WRIST-ELBOW).length
    delta=wrist-SHOULDER;distance=delta.length
    assert abs(l1-l2)<distance<l1+l2, 'Unreachable wrist target'
    axis=delta.normalized()
    along=(l1*l1-l2*l2+distance*distance)/(2*distance)
    hint=ELBOW-SHOULDER
    bend=(hint-axis*hint.dot(axis)).normalized()
    elbow=SHOULDER+axis*along+bend*math.sqrt(max(0,l1*l1-along*along))
    upper=(ELBOW-SHOULDER).rotation_difference(elbow-SHOULDER)
    lower=(WRIST-ELBOW).rotation_difference(wrist-elbow)
    return elbow,upper,lower


def deformed(point,row,shield=False):
    wrist=Vector(row['wrist_m'])
    lean=Matrix.Rotation(math.radians(row['lean_deg']),3,'X')
    p=point.copy()
    if shield:
        rotation=(Matrix.Rotation(math.radians(row['shield_yaw_deg']),3,'Z') @
                  Matrix.Rotation(math.radians(row['shield_tilt_deg']),3,'X'))
        p=wrist+rotation@(p-WRIST)
        return PIVOT+lean@(p-PIVOT)
    # Blend at shoulder and elbow for continuous anatomy; fingers follow wrist rigidly.
    if p.x>.22 and .86<p.z<1.53:
        elbow,upper,lower=arm_pose(wrist)
        up=SHOULDER+upper@(p-SHOULDER)
        low=elbow+lower@(p-ELBOW)
        forearm=1-smooth(1.105,1.205,p.z)
        q=up.lerp(low,forearm)
        arm_weight=smooth(.22,.31,p.x)*(1-smooth(1.43,1.53,p.z))
        p=p.lerp(q,arm_weight)
    amount=smooth(.96,1.12,point.z)
    return p.lerp(PIVOT+lean@(p-PIVOT),amount)


def make_hero():
    root=bpy.data.objects.new('Hero motion review',None)
    bpy.context.scene.collection.objects.link(root)
    base.GROUP=root
    shield_objects=[]
    original=base.make_shield
    def capture_shield():
        before=set(bpy.data.objects)
        original()
        shield_objects.extend(set(bpy.data.objects)-before)
    base.make_shield=capture_shield
    try: base.make_hero()
    finally: base.make_shield=original
    bpy.context.view_layer.update()
    for obj in root.children_recursive:
        if obj.type!='MESH':continue
        # Apply thickness before keys, preserving detail across all poses.
        bpy.context.view_layer.objects.active=obj
        for mod in list(obj.modifiers): bpy.ops.object.modifier_apply(modifier=mod.name)
        matrix=obj.matrix_world.copy();inverse=matrix.inverted()
        original_points=[matrix@v.co for v in obj.data.vertices]
        basis=obj.shape_key_add(name='Basis')
        for vertex,point in zip(basis.data,original_points):
            vertex.co=inverse@deformed(point,DATA['parry'][0],obj in shield_objects)
        keys=[]
        for row in DATA['parry'][1:-1]:
            key=obj.shape_key_add(name=row['id'])
            for vertex,point in zip(key.data,original_points):
                vertex.co=inverse@deformed(point,row,obj in shield_objects)
            keys.append((row,key))
        for row,key in keys:
            for pose in DATA['parry']:
                key.value=float(row['id']==pose['id'])
                key.keyframe_insert('value',frame=pose['frame'])
    root['left_hand']='anatomical left (+X), front -Y'
    root['status']='awaiting pose and motion approval'
    root['animation_method']='continuous mesh shape keys; gameplay not modified'
    return root


def make_melee():
    root=bpy.data.objects.new('Melee raised sword review',None)
    bpy.context.scene.collection.objects.link(root);base.GROUP=root
    base.make_skeleton('melee')
    bpy.context.view_layer.update()
    grip=Vector(DATA['melee']['grip_m'])
    direction=Vector(DATA['melee']['sword_direction']).normalized()
    old=Vector((-.19,-.11,-.70))-Vector((-.025,-.03,-.15))
    rotation=old.normalized().rotation_difference(direction).to_matrix().to_4x4()
    transform=Matrix.Translation(grip)@rotation@Matrix.Translation(-grip)
    for obj in root.children_recursive:
        if obj.name.startswith(('Sword hilt','Sword crossguard','Steel sword blade')):
            obj.matrix_world=transform@obj.matrix_world
    return root


def visible(root,value):
    for obj in root.children_recursive:obj.hide_render=not value


def main():
    base.validate()
    assert DATA['parry'][0]['wrist_m']==DATA['parry'][-1]['wrist_m']
    assert all(row['frame']<nxt['frame'] for row,nxt in zip(DATA['parry'],DATA['parry'][1:]))
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for row in base.DATA['palette']:base.material(row)
    hero=make_hero();melee=make_melee();base.GROUP=None
    base.setup_scene()
    scene=bpy.context.scene
    scene.render.fps=DATA['preview']['fps'];scene.frame_start=1;scene.frame_end=25
    settings=dict(base.DATA['render'][0],resolution_px=480,samples=16,orthographic_scale_m=2.6)
    visible(melee,False)
    scene.frame_set(1)
    for azimuth in (0,90,180,270):
        base.render_view(hero,azimuth,settings,OUT/f'hero-idle-{azimuth}.png')
    for row in DATA['parry']:
        scene.frame_set(row['frame'])
        base.render_view(hero,30,settings,OUT/f'hero-{row["id"]}.png')
    for frame in range(1,26):
        scene.frame_set(frame)
        base.render_view(hero,30,settings,OUT/f'parry-{frame:02}.png')
    visible(hero,False);visible(melee,True)
    for azimuth in (0,30,90,180):
        base.render_view(melee,azimuth,settings,OUT/f'melee-ready-{azimuth}.png')
    visible(melee,False);visible(hero,True);scene.frame_set(1)
    melee.hide_set(True)
    for obj in melee.children_recursive:obj.hide_set(True)
    scene.camera.location=(2.6,-4.5,2.0)
    scene.camera.rotation_euler=(Vector((0,0,.94))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shield-attack-motion-review.blend'))
    (OUT/'manifest.json').write_text(json.dumps(DATA,indent=2),encoding='utf-8')
    print('MOTION_REVIEW_COMPLETE')


if __name__=='__main__':main()
