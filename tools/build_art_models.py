"""Blender background script: concept-faithful review meshes, never runtime assets.

Run: blender --background --factory-startup --python tools/build_art_models.py
Geometry and camera dimensions are in metres. Art sheets are the source of truth.
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'art' / 'model-review-v1'
OUT.mkdir(parents=True, exist_ok=True)
DATA = json.loads((ROOT / 'data/art_models.json').read_text(encoding='utf-8'))
random.seed(17)
M = {}
GROUP = None


def validate():
    def walk(value, path='art'):
        if isinstance(value, dict):
            for key, cell in value.items():
                walk(cell, path + '.' + key)
        elif isinstance(value, list):
            assert value, path
            for index, cell in enumerate(value):
                walk(cell, path + '.' + str(index))
        else:
            assert value is not None and value != '', path
    walk(DATA)
    for row in DATA['characters']:
        assert (ROOT / row['concept']).is_file(), row
        assert (ROOT / row['equipment_concept']).is_file(), row
    assert len({r['azimuth_deg'] for r in DATA['views']}) == 8


def material(row):
    rgb = [int(row['hex'][i:i+2], 16) / 255 for i in (0, 2, 4)]
    # Source palette is sRGB; node inputs are scene-linear.
    rgb = [v / 12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    m = bpy.data.materials.new(row['id'])
    m.diffuse_color = (*rgb, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*rgb, 1)
    bsdf.inputs['Roughness'].default_value = row['roughness']
    bsdf.inputs['Metallic'].default_value = row['metallic']
    if row['id'] in ('gem', 'violet'):
        bsdf.inputs['Emission Color'].default_value = (*rgb, 1)
        bsdf.inputs['Emission Strength'].default_value = .3
    M[row['id']] = m


def attach(obj, name, mat):
    obj.name = name
    if obj.type == 'MESH':
        obj.data.materials.append(M[mat])
    if GROUP is not None:
        obj.parent = GROUP
    return obj


def mesh(name, verts, faces, mat):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return attach(obj, name, mat)


def ell(name, center, scale, mat, segments=16, rings=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=center)
    obj = attach(bpy.context.object, name, mat)
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def block(name, center, scale, mat, bevel=.01):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = attach(bpy.context.object, name, mat)
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new('Soft worn edges', 'BEVEL')
        mod.width, mod.segments = bevel, 2
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def tube(name, points, radii, mat, sides=10):
    verts, faces = [], []
    for i, xyz in enumerate(points):
        here = Vector(xyz)
        tangent = Vector(points[min(i+1, len(points)-1)]) - Vector(points[max(0, i-1)])
        tangent.normalize()
        u = tangent.cross(Vector((0, 1, 0)))
        if u.length < .01:
            u = tangent.cross(Vector((1, 0, 0)))
        u.normalize()
        v = tangent.cross(u).normalized()
        radius = radii[i] if isinstance(radii, list) else radii
        for j in range(sides):
            angle = 2*math.pi*j/sides
            verts.append(tuple(here + radius * (math.cos(angle)*u + math.sin(angle)*v)))
    for i in range(len(points)-1):
        for j in range(sides):
            a=i*sides+j; b=i*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
    faces.extend([tuple(reversed(range(sides))),tuple((len(points)-1)*sides+j for j in range(sides))])
    return mesh(name, verts, faces, mat)


def loft(name, rows, mat, sides=20):
    # Rows: centre xyz, elliptical half width/depth.
    verts, faces = [], []
    for x,y,z,rx,ry in rows:
        for j in range(sides):
            a=2*math.pi*j/sides
            verts.append((x+rx*math.cos(a),y+ry*math.sin(a),z))
    for i in range(len(rows)-1):
        for j in range(sides):
            a=i*sides+j; b=i*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
    faces.extend([tuple(reversed(range(sides))),tuple((len(rows)-1)*sides+j for j in range(sides))])
    return mesh(name,verts,faces,mat)


def ring(name, center, radius, thickness, mat, front=False):
    points=[]
    for i in range(49):
        a=2*math.pi*i/48
        points.append((center[0]+radius*math.cos(a),
                       center[1] if front else center[1]+radius*math.sin(a),
                       center[2]+radius*math.sin(a) if front else center[2]))
    return tube(name,points,thickness,mat,8)


def rivet(name, xyz, radius=.009):
    return ell(name,xyz,(radius,radius*.55,radius),'bronze',8,6)


def leather_band(name, center, radius_x, radius_y, height, mat='leather'):
    return loft(name,[(center[0],center[1],center[2]-height/2,radius_x,radius_y),
                     (center[0],center[1],center[2]+height/2,radius_x,radius_y)],mat)


def fur_band(name, center, rx, ry, height):
    leather_band(name,center,rx,ry,height*.8,'fur')
    for j in range(24):
        a=2*math.pi*j/24
        x,y=center[0]+rx*math.cos(a),center[1]+ry*math.sin(a)
        tipz=center[2]-height*(.35+random.random()*.5)
        obj=mesh(name+' tuft',[(x-.018,y-.008,center[2]+height*.4),
                              (x+.018,y+.008,center[2]+height*.4),
                              (x+.02*math.cos(a),y+.02*math.sin(a),tipz)],[(0,1,2)],
                 'fur_light' if j%3 else 'fur')
        solid=obj.modifiers.new('Tuft thickness','SOLIDIFY');solid.thickness=.009


def join_skin(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects: obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.join()
    obj=objects[0]
    obj.name='Continuous sculpted muscular body'
    mod=obj.modifiers.new('Continuous anatomy','REMESH')
    mod.mode='VOXEL';mod.voxel_size=.0075;mod.use_smooth_shade=False
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=obj.modifiers.new('Sculpt surface relaxation','SMOOTH');mod.factor=.65;mod.iterations=4
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=obj.modifiers.new('Sculpt facets','DECIMATE');mod.ratio=.16
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def make_hero():
    skin=[]
    skin.append(loft('Torso',[(0,0,.81,.14,.11),(0,.01,.95,.155,.105),
         (0,.015,1.09,.17,.115),(0,.02,1.23,.23,.14),
         (0,.025,1.38,.285,.14),(0,.03,1.46,.255,.10),
         (0,.025,1.49,.10,.08)],'skin',24))
    skin.append(ell('Neck',(0,.015,1.51),(.085,.085,.12),'skin'))
    for s in (-1,1):
        skin.append(ell('Pectoral',(s*.135,-.105,1.355),(.152,.085,.105),'skin'))
        skin.append(ell('Upper trapezius',(s*.135,.02,1.44),(.15,.10,.06),'skin'))
        skin.append(ell('Back lat',(s*.16,.10,1.27),(.12,.05,.16),'skin'))
        for i in range(3):
            skin.append(ell('Abdominal',(s*.053,-.106,1.22-i*.072),(.052,.025,.047),'skin'))
        skin.append(ell('Deltoid',(s*.29,.015,1.38),(.115,.12,.12),'skin'))
        shoulder=(s*.30,.01,1.39);elbow=(s*.405,-.015,1.15)
        wrist=(s*.44,-.10,.98)
        if s==1: wrist=(.405,-.23,1.045)
        skin.append(tube('Upper arm',[shoulder,(s*.36,-.005,1.29),elbow],[.097,.10,.071],'skin',16))
        skin.append(ell('Biceps',(s*.365,-.063,1.265),(.07,.075,.10),'skin'))
        skin.append(tube('Forearm',[elbow,((elbow[0]+wrist[0])/2,-.08,1.075),wrist], [.069,.077,.046],'skin',16))
        skin.append(ell('Palm',(wrist[0],wrist[1]-.009,wrist[2]-.058),(.054,.039,.072),'skin'))
        # Four fingers remain separate enough to read when enlarged for model review.
        for f in range(4):
            x=wrist[0]-.035+f*.023
            skin.append(tube('Finger',[(x,wrist[1]-.015,wrist[2]-.09),
                (x,wrist[1]-.036,wrist[2]-.14),(x,wrist[1]-.005,wrist[2]-.15)], [.012,.012,.009],'skin',8))
        skin.append(tube('Thumb',[(wrist[0]-s*.044,wrist[1]-.018,wrist[2]-.045),
                  (wrist[0]-s*.065,wrist[1]-.054,wrist[2]-.087)],.018,'skin',8))
        x=s*.135
        skin.append(loft('Leg',[(x,0,.90,.12,.12),(x*1.05,0,.76,.13,.12),
            (x*1.1,-.015,.58,.092,.085),(x*1.15,-.022,.50,.075,.075),
            (x*1.17,.015,.35,.086,.08),(x*1.18,0,.17,.055,.057)],'skin',18))
        skin.append(ell('Kneecap',(x*1.1,-.067,.52),(.066,.045,.068),'skin'))
    join_skin(skin)
    # Face: cheekbones, angular jaw, brows, eyes, nose and beard are true geometry.
    loft('Angular head',[(0,0,1.55,.065,.067),(0,-.005,1.58,.092,.085),
        (0,.005,1.65,.108,.092),(0,.015,1.73,.108,.095),
        (0,.02,1.79,.078,.078)],'skin',20)
    for s in (-1,1):
        ell('Ear',(s*.108,.008,1.67),(.025,.022,.044),'skin')
        ell('Ear hollow',(s*.123,-.008,1.672),(.009,.009,.024),'skin_dark',10,6)
        cheek=ell('Cheekbone',(s*.061,-.067,1.648),(.047,.035,.028),'skin_light')
        eye=ell('Eye socket',(s*.045,-.082,1.693),(.035,.014,.014),'skin_dark')
        ell('Eye',(s*.043,-.094,1.693),(.023,.005,.006),'fur_light',12,6)
        ell('Iris',(s*.042,-.099,1.693),(.006,.003,.006),'hair',10,6)
        brow=tube('Strong brow',[(s*.013,-.094,1.717),(s*.04,-.10,1.723),(s*.075,-.087,1.714)],.014,'hair',8)
    nose=loft('Nose',[(0,-.106,1.655,.026,.022),(0,-.115,1.675,.021,.03),
                      (0,-.084,1.716,.014,.018)],'skin_light',10)
    tube('Mouth',[(-.033,-.088,1.624),(0,-.103,1.619),(.033,-.088,1.624)],.004,'skin_dark',6)
    for s in (-1,1):
        tube('Moustache',[(s*.005,-.108,1.64),(s*.025,-.105,1.638),(s*.045,-.087,1.628)], [.007,.009,.004],'hair',8)
        tube('Beard jaw',[(s*.09,-.038,1.66),(s*.074,-.078,1.605),(s*.03,-.085,1.576)], [.012,.021,.023],'hair',10)
    ell('Beard chin',(0,-.067,1.582),(.046,.032,.024),'hair')
    # Hair cap is an open shell, leaving the face entirely exposed.
    verts=[];faces=[]
    for r in range(7):
        for j in range(28):
            a=2*math.pi*j/28
            front=(1-math.sin(a))/2
            phi=(r/6)*(.75+ .88*(1-front))
            verts.append((.116*math.sin(phi)*math.cos(a),.021+.105*math.sin(phi)*math.sin(a),1.725+.095*math.cos(phi)))
    for r in range(6):
        for j in range(28): faces.append((r*28+j,r*28+(j+1)%28,(r+1)*28+(j+1)%28,(r+1)*28+j))
    mesh('Swept-back hair cap',verts,faces,'hair')
    for j in range(15):
        x=(j-7)*.014
        side=abs(x)/.10
        tube('Swept hair lock',[(x,-.050,1.79-.025*side),
                  (x*.95,-.023,1.818-.012*side),(x*.84,.015,1.831-.01*side),
                  (x*.72,.055,1.821-.02*side),(x*.63,.09,1.79-.025*side),
                  (x*.4,.125,1.735)], [.011,.015,.017,.017,.014,.004],
                  'hair_light' if j%4==0 else 'hair',8)
    for s in (-1,1):
        for j in range(4):
            tube('Long swept temple lock',[(s*.075,-.054,1.777-j*.009),
                 (s*.111,-.015,1.759-j*.013),(s*.116,.035,1.715-j*.015),
                 (s*.086,.091,1.692-j*.01)], [.012,.014,.013,.003],'hair',8)
    tube('Loose forehead curl',[(-.036,-.066,1.802),(-.065,-.082,1.798),
        (-.078,-.087,1.77),(-.07,-.088,1.746)], [.009,.011,.01,.002],'hair_light',8)
    ell('Hair tie',(0,.126,1.72),(.046,.032,.032),'leather')
    for j in range(7):
        x=(j-3)*.012
        tube('Ponytail',[(x,.14,1.72),(x*1.6,.18,1.69),(x*1.8,.197,1.65),
                    (x*1.7+.018,.18,1.59),(x+.038,.20,1.55)], [.016,.021,.022,.016,.002],
                    'hair_light' if j%3==0 else 'hair',8)
    # Broad leather belt, fur-lined overlapping skirt, bracers and heavy boots.
    leather_band('Waist belt',(0,0,.96),.18,.125,.10)
    block('Iron belt buckle',(0,-.137,.963),(.095,.022,.074),'steel',.008)
    block('Buckle inset',(0,-.152,.963),(.065,.009,.047),'leather',.003)
    block('Buckle tongue',(.002,-.16,.963),(.012,.007,.055),'steel',.002)
    for j in range(10):
        a=2*math.pi*j/10
        rivet('Belt rivet',(.18*math.cos(a),.132*math.sin(a),.965))
    leather_band('Shorts',(0,.01,.81),.185,.12,.21,'iron')
    for j in range(12):
        a=2*math.pi*j/12
        tip=.70+random.random()*.07
        points=[]
        for z,angle,radius in [(.93,a-.29,.175),(.93,a+.29,.175),
                                 (.77,a+.25,.205),(tip,a,.22),(.77,a-.25,.205)]:
            points.append((radius*math.cos(angle),radius*.70*math.sin(angle),z))
        obj=mesh('Layered leather skirt panel',points,[(0,1,2,3,4)],'leather_light' if j%3 else 'leather')
        sol=obj.modifiers.new('Leather thickness','SOLIDIFY');sol.thickness=.012
        tube('Fur skirt hem',points[2:5],[.02,.028,.02],'fur',8)
        rivet('Skirt rivet',(points[0][0],points[0][1]-.007, .91),.007)
    for s in (-1,1):
        wx,wy,wz=(s*.44,-.10,.98) if s==-1 else (.405,-.23,1.045)
        obj=tube('Leather bracer',[(wx,wy,wz+.01),(s*.415,wy+.04,wz+.13)], [.059,.076],'leather',14)
        for z in (.04,.10):
            leather_band('Bracer strap',(wx,wy,wz+z),.064,.065,.022,'leather_light')
            block('Bracer buckle',(wx,wy-.068,wz+z),(.033,.012,.023),'steel',.003)
        x=s*.159
        loft('Heavy leather boot',[(x,-.01,.07,.076,.12),(x,.0,.15,.068,.073),
                      (x,0,.32,.081,.076),(x,0,.39,.085,.08)],'leather',16)
        block('Boot toe',(x,-.064,.075),(.16,.265,.115),'leather_light',.035)
        block('Boot sole',(x,-.05,.023),(.172,.28,.038),'hair',.012)
        fur_band('Boot fur',(x,0,.385),.087,.083,.055)
        for z in (.19,.30):
            leather_band('Boot strap',(x,0,z),.087,.085,.023,'leather_light')
            block('Boot buckle',(x-s*.045,-.076,z),(.04,.015,.028),'steel',.003)
    # Fine chest scars stay visible in the enlarged model without changing silhouette.
    tube('Chest scar',[(-.15,-.18,1.415),(-.11,-.19,1.386),(-.074,-.17,1.35)],.0028,'skin_light',6)
    make_shield()


def make_shield():
    cx,cy,cz=.43,-.315,1.105
    radius=.345
    # Back planks, bronze rim, four braces, central turquoise jewel and geometric runes.
    loft_obj=loft('Shield disc',[(0,0,-.022,radius,radius),(0,0,.022,radius,radius)],'iron',64)
    loft_obj.rotation_euler[0]=math.pi/2
    loft_obj.location=(cx,cy,cz)
    ring('Shield bronze rim',(cx,cy-.02,cz),radius,.018,'bronze',True)
    ring('Shield inner inset',(cx,cy-.026,cz),radius*.87,.006,'bronze_dark',True)
    for i in range(9):
        x=-radius+.04+i*.075
        length=2*math.sqrt(max(0,radius*radius-x*x))
        block('Shield wooden back plank',(cx+x,cy+.03,cz),(.068,.018,length*.95),'leather_light',.003)
    for angle in (0,math.pi/2,math.pi,math.pi*1.5):
        points=[]
        for rr,ww in [(.065,-.018),(.32,-.027),(.32,.027),(.065,.018)]:
            points.append((cx+rr*math.cos(angle)+ww*math.sin(angle),cy-.047,
                           cz+rr*math.sin(angle)-ww*math.cos(angle)))
        obj=mesh('Bronze radial shield brace',points,[(0,1,2,3)],'bronze')
        sol=obj.modifiers.new('Brace thickness','SOLIDIFY');sol.thickness=.009
    ell('Shield central boss',(cx,cy-.04,cz),(.083,.032,.083),'bronze',24,12)
    gem=ell('Turquoise shield heart',(cx,cy-.078,cz),(.031,.020,.041),'gem',8,4)
    for i in range(16):
        a=2*math.pi*i/16
        rivet('Rim rivet',(cx+.322*math.cos(a),cy-.04,cz+.322*math.sin(a)),.009)
        b=a+math.pi/16
        ox,oz=cx+.238*math.cos(b),cz+.238*math.sin(b)
        # Each rune has two or three raised strokes; no baked front-facing decal.
        for k,(u,v) in enumerate([((-.012,-.02),(.0,.023)),((0,.023),(.015,.005))]):
            tube('Raised shield rune',[(ox+u[0],cy-.034,oz+u[1]),(ox+v[0],cy-.034,oz+v[1])],.004,'bronze',6)
    for x in (-.1,.1):
        tube('Shield back arm strap',[(cx+x,cy+.055,cz-.10),(cx+x,cy+.10,cz),
                                    (cx+x,cy+.055,cz+.1)],.018,'leather',10)


def bone(name,a,b,r=.025):
    a,b=Vector(a),Vector(b)
    tube(name,[a,a.lerp(b,.18),a.lerp(b,.8),b],[r*1.25,r*.75,r*.7,r*1.2],'bone',10)
    for xyz in (a,b): ell(name+' joint',xyz,(r*1.3,r*1.15,r*1.2),'bone',12,8)


def skull():
    block('Skull cranium',(0,0,1.64),(.205,.18,.224),'bone',.065)
    for s in (-1,1):
        ell('Temple',(s*.092,-.01,1.62),(.035,.06,.065),'bone')
        eye=ell('Dark recessed eye socket',(s*.047,-.092,1.665),(.036,.013,.028),'void',12,8)
        ell('Faint violet eye',(s*.047,-.106,1.665),(.008,.004,.009),'violet',10,6)
        tube('Brow ridge',[(s*.012,-.10,1.70),(s*.052,-.105,1.708),(s*.082,-.09,1.691)],.011,'bone',8)
        ell('Cheek arch',(s*.072,-.072,1.615),(.025,.035,.019),'bone')
    mesh('Nasal cavity',[(-.018,-.101,1.637),(.018,-.101,1.637),(0,-.113,1.612)],[(0,1,2)],'void')
    block('Mouth cavity',(0,-.071,1.586),(.12,.035,.044),'void',.012)
    tube('Jaw bone',[(-.081,-.005,1.61),(-.076,-.043,1.565),(0,-.075,1.553),
                    (.076,-.043,1.565),(.081,-.005,1.61)],.016,'bone',10)
    for j in range(7):
        x=(j-3)*.015
        block('Upper tooth',(x,-.091,1.594),(.012,.014,.022),'bone',.003)
        block('Lower tooth',(x,-.087,1.57),(.012,.012,.014),'bone',.003)


def make_skeleton(kind):
    skull()
    for i in range(12):
        ell('Spinal vertebra',(0,.055,.88+i*.044),(.028,.027,.023),'bone',10,6)
    bone('Sternum',(0,-.112,1.16),(0,-.112,1.40),.018)
    for i in range(6):
        z=1.38-i*.045; width=.164-i*.01
        for s in (-1,1):
            tube('Individual curved rib',[(0,.055,z),(s*width*.8,.04,z+.01),
                (s*width,.0,z-.01),(s*width*.85,-.09,z-.028),
                (s*.025,-.115,z-.045)],.014,'bone',8)
    for s in (-1,1):
        bone('Clavicle',(0,-.07,1.42),(s*.22,-.015,1.425),.024)
        bone('Neck',(0,0,1.4),(0,0,1.545),.025)
        tube('Pelvis arch',[(0,.035,.98),(s*.11,.02,1.00),(s*.14,-.04,.93),
             (s*.08,-.095,.88),(0,-.08,.91)],.032,'bone',10)
        hip=(s*.11,0,.91);knee=(s*.16,-.01,.52);ankle=(s*.175,0,.12)
        bone('Femur',hip,knee,.033)
        bone('Tibia',knee,ankle,.025)
        bone('Fibula',(s*.18,.015,.50),(s*.20,.015,.14),.013)
        for f in range(4):
            bone('Foot bone',(s*.175+(f-1.5)*.022,-.005,.08),
                 (s*.175+(f-1.5)*.025,-.15,.045),.011)
        shoulder=(s*.225,0,1.42);elbow=(s*.31,-.02,1.20)
        wrist=(s*.35,-.11,1.005)
        if kind=='ranged' and s==-1: elbow=(-.35,-.015,1.27);wrist=(-.43,-.13,1.20)
        bone('Humerus',shoulder,elbow,.026)
        bone('Radius',elbow,wrist,.019)
        bone('Ulna',(elbow[0]+.024,elbow[1]+.012,elbow[2]),
             (wrist[0]+.018,wrist[1]+.012,wrist[2]),.013)
        ell('Hand bones',(wrist[0],wrist[1]-.01,wrist[2]-.035),(.039,.024,.048),'bone')
        for f in range(4):
            x=wrist[0]+(f-1.5)*.015
            bone('Finger bones',(x,wrist[1]-.018,wrist[2]-.05),
                 (x,wrist[1]-.037,wrist[2]-.098),.008)
    leather_band('Skeleton belt',(0,0,.94),.145,.10,.067)
    block('Skeleton bronze buckle',(0,-.11,.94),(.07,.025,.057),'bronze',.006)
    # Ragged burgundy skirt, with true thickness and front/back folds.
    for j in range(10):
        a=2*math.pi*j/10
        z=.68+random.random()*.09
        verts=[(.15*math.cos(a-.3),.105*math.sin(a-.3),.92),
               (.15*math.cos(a+.3),.105*math.sin(a+.3),.92),
               (.18*math.cos(a+.27),.12*math.sin(a+.27),z+.035),
               (.18*math.cos(a),.12*math.sin(a),z-.04),
               (.18*math.cos(a-.27),.12*math.sin(a-.27),z+.01)]
        obj=mesh('Ragged cloth strip',verts,[(0,1,2,3,4)],'cloth' if j%2 else 'cloth_light')
        sol=obj.modifiers.new('Cloth thickness','SOLIDIFY');sol.thickness=.009
    if kind=='melee':
        # Bronze open-face helmet and three armour plates match the approved fighter.
        loft('Open bronze helmet',[(0,.025,1.69,.118,.106),(0,.025,1.75,.116,.104),
                 (0,.025,1.81,.065,.063),(0,.025,1.825,.014,.015)],'bronze',24)
        tube('Helmet brow trim',[(-.115,-.045,1.71),(0,-.10,1.72),(.115,-.045,1.71)],.012,'bronze_dark')
        for j in range(9):
            y=-.055+j*.019
            tube('Helmet crest',[(0,y,1.79),(0,y,1.86)], [.018,.014],'bronze_dark',8)
        for i in range(3):
            ell('Layered iron shoulder plate',(.22+i*.025,.0,1.43-i*.042),(.105,.12,.055),'iron',16,8)
            tube('Shoulder gold edge',[(.14+i*.025,-.08,1.43-i*.042),(.23+i*.025,-.12,1.42-i*.042),
                                     (.31+i*.025,-.06,1.41-i*.042)],.007,'bronze',8)
        for s in (-1,1):
            leather_band('Arm guard',(s*.335,-.07,1.08),.039,.036,.14,'leather')
            block('Bronze shin guard',(s*.18,-.028,.28),(.075,.055,.245),'bronze_dark',.015)
        # Sword is a tapered metal mesh, not a rectangle.
        x,y,z=-.35,-.12,.92
        tube('Sword hilt',[(x,y,z-.01),(x-.025,y-.03,z-.15)],.019,'leather',10)
        tube('Sword crossguard',[(x-.09,y-.03,z-.14),(x+.055,y-.03,z-.165)],.017,'bronze',8)
        mesh('Steel sword blade',[(x-.045,y-.03,z-.16),(x+.025,y-.03,z-.18),
             (x-.13,y-.11,z-.65),(x-.19,y-.11,z-.70),(x-.18,y-.11,z-.59),
             (x-.077,y-.039,z-.17),(x-.16,y-.125,z-.61)],
             [(0,1,6,5),(1,2,3,6),(6,3,4,5),(5,4,0)],'steel')
    else:
        # Hood is an open shell; face is not painted onto a solid cone.
        rows=[(1.47,.16,.125),(1.60,.15,.13),(1.74,.145,.13),(1.83,.095,.09),(1.85,.025,.03)]
        verts=[];faces=[];sides=18
        for z,rx,ry in rows:
            for j in range(sides):
                a=-.42+(math.pi+.84)*j/(sides-1)
                verts.append((rx*math.cos(a),.018+ry*math.sin(a),z))
        for i in range(len(rows)-1):
            for j in range(sides-1):
                a=i*sides+j;faces.append((a,a+1,a+1+sides,a+sides))
        obj=mesh('Open burgundy hood',verts,faces,'cloth')
        sol=obj.modifiers.new('Hood lining','SOLIDIFY');sol.thickness=.014
        # Shoulder mantle has a front split so the ribs remain visible.
        for s in (-1,1):
            mesh('Shoulder mantle',[(s*.02,-.12,1.47),(s*.22,-.07,1.43),
                 (s*.285,.0,1.34),(s*.18,.15,1.37),(s*.01,.13,1.48)],
                 [(0,1,2),(0,2,3),(0,3,4)],'cloth_light')
        for j in range(8):
            a=math.pi*j/7
            mesh('Tattered back cloak',[(.21*math.cos(a),.10*math.sin(a)+.04,1.42),
                 (.21*math.cos(a+.3),.10*math.sin(a+.3)+.04,1.42),
                 (.24*math.cos(a+.3),.13*math.sin(a+.3)+.04,.65+random.random()*.12),
                 (.24*math.cos(a),.13*math.sin(a)+.04,.57+random.random()*.12)],[(0,1,2,3)],'cloth')
        # Curved wooden staff with a bronze claw and a violet crystal.
        x,y=.36,-.13
        tube('Mage staff',[(x,y,.05),(x+.01,y,1.05),(x-.01,y,1.56)],.021,'leather_light',12)
        for s in (-1,1):
            tube('Staff bronze claw',[(x,y,1.54),(x+s*.09,y,1.62),
                 (x+s*.08,y,1.74),(x+s*.055,y,1.79)], [.018,.018,.013,.007],'bronze',8)
        ell('Violet staff crystal',(x,y,1.72),(.052,.044,.105),'violet',6,4)
        for z in (.23,.55,1.15,1.43): ring('Staff binding',(x,y,z),.025,.006,'bronze')


def normalize(root, height):
    objects=[obj for obj in root.children_recursive if obj.type=='MESH']
    # Character body height excludes the staff and helmet crest; shared feet anchor.
    points=[obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    assert points and all(math.isfinite(v) for pt in points for v in pt)
    # Model units are already authored at 1.8m; preserve equipment extending outside the body.
    root['body_height_m']=height
    root['foot_anchor']=[0.0,0.0,0.0]
    root['front_axis']='-Y'
    root['review_status']='awaiting_user_approval'
    return {'meshes':len(objects),'vertices':sum(len(obj.data.vertices) for obj in objects),
            'z_min_m':min(v.z for v in points),'z_max_m':max(v.z for v in points)}


def setup_scene():
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.device='CPU'
    scene.cycles.samples=24
    scene.cycles.use_denoising=True
    scene.render.threads_mode='FIXED';scene.render.threads=6
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGBA'
    scene.render.film_transparent=True
    bpy.context.preferences.filepaths.save_version=0
    scene.view_settings.view_transform='Standard'
    scene.world.color=(.18,.18,.18)
    for name,position,power,size in [('Key',(-3,-4,6),420,4),('Fill',(3,-1,3),170,3),('Rim',(1,3,4),300,3)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=position
        obj.rotation_euler=(Vector((0,0,1))-obj.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('Orthographic review camera')
    camera=bpy.data.objects.new('Orthographic review camera',data)
    scene.collection.objects.link(camera);scene.camera=camera;data.type='ORTHO'


def render_view(root, azimuth, settings, path):
    scene=bpy.context.scene
    angle=math.radians(azimuth);elev=math.radians(settings['elevation_deg'])
    target=Vector((0,0,.94))
    scene.camera.location=target+Vector((4*math.sin(angle)*math.cos(elev),-4*math.cos(angle)*math.cos(elev),4*math.sin(elev)))
    scene.camera.rotation_euler=(target-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.ortho_scale=settings['orthographic_scale_m']
    scene.render.resolution_x=scene.render.resolution_y=settings['resolution_px']
    scene.render.resolution_percentage=100
    scene.cycles.samples=settings['samples']
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)


def main():
    global GROUP
    validate()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for row in DATA['palette']: material(row)
    roots=[];stats={}
    for row in DATA['characters']:
        GROUP=bpy.data.objects.new(row['id']+' model',None)
        bpy.context.scene.collection.objects.link(GROUP)
        GROUP['concept']=row['concept']
        if row['id']=='hero': make_hero()
        else: make_skeleton(row['id'])
        bpy.context.view_layer.update()
        stats[row['id']]=normalize(GROUP,row['height_m'])
        roots.append(GROUP)
    GROUP=None
    setup_scene()
    for root in roots:
        for obj in root.children_recursive: obj.hide_render=True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shield-attack-review.blend'))
    manifest={'status':'awaiting_user_approval','model_stats':stats,
              'runtime_modified':False,'views':DATA['views'],'render':DATA['render']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    # Optional quick pass: one front-three-quarter image of each character.
    quick='--quick' in sys.argv
    for row,root in zip(DATA['characters'],roots):
        for obj in root.children_recursive: obj.hide_render=False
        bpy.ops.object.select_all(action='DESELECT')
        root.select_set(True)
        for obj in root.children_recursive: obj.select_set(True)
        bpy.context.view_layer.objects.active=root
        bpy.ops.export_scene.gltf(filepath=str(OUT/(row['id']+'.glb')),export_format='GLB',
                                  use_selection=True,export_apply=True)
        render_view(root,30,DATA['render'][0],OUT/(row['id']+'-three-quarter.png'))
        if not quick:
            for view in DATA['views']:
                render_view(root,view['azimuth_deg'],DATA['render'][0],OUT/(row['id']+'-'+view['id']+'.png'))
                render_view(root,view['azimuth_deg'],DATA['render'][1],OUT/(row['id']+'-game-'+view['id']+'.png'))
        for obj in root.children_recursive: obj.hide_render=True
    # Leave the hero visible in the saved review scene.
    for obj in roots[0].children_recursive: obj.hide_render=False
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shield-attack-review.blend'))
    print('REVIEW_MODELS_COMPLETE',json.dumps(stats))


if __name__=='__main__':
    main()
