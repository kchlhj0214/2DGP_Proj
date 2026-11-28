"""Write a PixelLab Workbench scene for one of the boss's articulated clips."""

import argparse
import json
from math import atan2, cos, degrees, pi, radians, sin

from tools.generate_data import ROOT

RIG = json.loads((ROOT / 'data/boss_rig.json').read_text(encoding='utf-8'))
DIRECTIONS = ('south', 'south-east', 'east', 'north-east', 'north', 'north-west', 'west', 'south-west')
OFFSET = (64, 36)
SUBFRAMES = 2
ATTACK_PHASES = {'charge': (4, 8), 'slam': (4, 4, 4), 'swing': (4, 4, 4)}


def expanded_rows(action):
    """Insert new articulated poses, including the seams of the looping strides."""
    rows = RIG['clips'][action]
    end = rows[0] if action == 'walk' else rows[4] if action == 'charge' else rows[-1]
    return [pose_row for first, second in zip(rows, [*rows[1:], end], strict=True)
            for pose_row in (first, [(a + b) / 2 for a, b in zip(first, second, strict=True)])]


def pair(point):
    return [round(point.real), round(point.imag)]


def rotated(point, pivot, angle):
    angle = radians(angle)
    return pivot + (point - pivot) * complex(cos(angle), sin(angle))


def plate(part, pivot):
    return {'layer': 'art', 'pivot': pair(pivot), 'at': list(OFFSET),
            'draw': [{'op': 'copy', 'part': part, 'method': 'scale2x8'}]}


def position(start, target, angle):
    return {'at': pair(complex(*OFFSET) + target - start), 'angle': round(angle, 2)}


def slope(start, end):
    step = end - start
    return degrees(atan2(step.imag, step.real))


def section(polygon, top, bottom):
    return {'include': [polygon], 'exclude': [
        [[0, 0], [256, 0], [256, top], [0, top]],
        [[0, bottom], [256, bottom], [256, 256], [0, 256]]],
    }


def leg_lining(start, end, width):
    a, b = complex(*start), complex(*end)
    vector = b - a
    side = vector * 1j / abs(vector) * width
    tip = b + vector * .07
    edges = [pair(a - side), pair(a + side), pair(tip + side * .65), pair(tip - side * .65)]
    return {'op': 'polygon', 'points': edges, 'color': '#3b2a24',
            'outline': '#241a17', 'stroke_width': 1}


def view_joints(view):
    pelvis, shoulder, elbow = (complex(*view[key]) for key in ('pelvis', 'shoulder', 'elbow'))
    free_shoulder = complex(*view.get('other_shoulder', view['shoulder']))
    return pelvis, shoulder, elbow, free_shoulder, complex(pelvis.real, 98)


def pose(view, motion, joints):
    name = view['id']
    pelvis, shoulder, elbow, free_shoulder, cape_pin = joints
    direction = pi / 4 * DIRECTIONS.index(name)
    forward = complex(sin(direction), .44 * cos(direction))
    side = -1 if name == 'south' else 1
    shift = forward * motion['lean'] + motion['drop'] * 1j
    tilt = forward.real * motion['tilt'] * .68
    if abs(forward.real) < .01:
        tilt = motion['tilt'] * (.19 if name == 'south' else -.19)
    upper_turn = tilt - side * motion['upper_arm']
    fore_turn = tilt - side * motion['forearm']
    posed_shoulder = rotated(shoulder, pelvis, tilt) + shift
    posed_elbow = rotated(elbow, shoulder, upper_turn) + posed_shoulder - shoulder
    result = {
        'torso': position(pelvis, pelvis + shift, tilt),
        'cape': position(cape_pin, rotated(cape_pin, pelvis, tilt) + shift, tilt - side * motion['cape']),
        'weapon_arm': position(shoulder, posed_shoulder, upper_turn),
        'grip': position(elbow, posed_elbow, fore_turn),
    }
    if 'other_arm' in view:
        result['free_arm'] = position(free_shoulder, rotated(free_shoulder, pelvis, tilt) + shift,
                                      tilt + side * motion['free_arm'])
    for index, (hip_xy, knee_xy, boot_xy, _) in enumerate(view['legs']):
        label = ('left', 'right')[index]
        hip, knee, boot = map(lambda point: complex(*point), (hip_xy, knee_xy, boot_xy))
        travel = forward * motion[f'{label}_stride']
        lift = motion[f'{label}_lift']
        posed_hip = rotated(hip, pelvis, tilt) + shift
        posed_boot = boot + travel - lift * 1j
        # The knee follows the weight shift and flexes forward as the boot clears the floor.
        knee_target = knee + .42 * (posed_hip - hip) + .48 * (posed_boot - boot) + forward * (.58 * lift)
        thigh_angle = slope(posed_hip, knee_target) - slope(hip, knee)
        posed_knee = rotated(knee, hip, thigh_angle) + posed_hip - hip
        boot_angle = slope(posed_knee, posed_boot) - slope(knee, boot)
        result[f'thigh_{index}'] = position(hip, posed_hip, thigh_angle)
        result[f'boot_{index}'] = position(knee, posed_knee, boot_angle)
    return result


def rig_view(view, rows, action):
    name = view['id']
    joints = view_joints(view)
    pelvis, shoulder, elbow, free_shoulder, cape_pin = joints
    arm = RIG['weapon_masks'][name]
    arm_set = section(arm, 0, round(elbow.imag + 7))
    grip = section(arm, round(elbow.imag - 5), 256)
    cape = RIG['cape'][name]
    parts = {'upper_arm': arm_set, 'grip': grip}
    nodes = {}
    exclusions = [arm]
    for index, (hip, knee, boot_point, mask) in enumerate(view['legs']):
        thigh = f'thigh_{index}'
        boot = f'boot_{index}'
        parts[thigh] = section(mask, 0, knee[1] + 6)
        parts[boot] = section(mask, knee[1] - 5, 256)
        parts[thigh]['exclude'].append(arm)
        parts[boot]['exclude'].append(arm)
        nodes[thigh] = plate(thigh, complex(*hip))
        nodes[boot] = plate(boot, complex(*knee))
        if name in ('east', 'south-east') and index == 0:
            # The original club covers this shin. Paint the narrow surface that the lifted weapon reveals.
            nodes[thigh]['draw'].insert(0, leg_lining(hip, knee, 7))
            nodes[boot]['draw'].insert(0, leg_lining(knee, boot_point, 7))
        exclusions.append(mask)
    if 'other_arm' in view:
        parts['free_arm'] = {'include': [view['other_arm']]}
        exclusions.append(view['other_arm'])
        nodes['free_arm'] = plate('free_arm', free_shoulder)
    parts['cape'] = {'include': [cape], 'exclude': exclusions.copy()}
    if action == 'stagger' and name in ('north-east', 'north'):
        # The cape covers the upper legs from behind. Keep those cloth folds on the cape.
        parts['cape']['exclude'] = [arm]
    # Preserve a strip inside the cape seam to keep it attached through the swing.
    cape_tail = [[0, 115], [256, 115], [256, 256], [0, 256]]
    parts['torso'] = {'exclude': [*exclusions, cape],
                      'include': [[[0,0],[256,0],[256,256],[0,256]]]}
    parts['cape_seam'] = {'include': [cape], 'exclude': [*exclusions, cape_tail]}
    nodes['cape'] = plate('cape', cape_pin)
    nodes['torso'] = plate('torso', pelvis)
    nodes['torso']['draw'].append({'op': 'copy', 'part': 'cape_seam'})
    nodes['weapon_arm'] = plate('upper_arm', shoulder)
    nodes['grip'] = plate('grip', elbow)
    frames = [f'frame-{index + 1}' for index in range(len(rows))]
    poses = {frame: pose(view, dict(zip(RIG['columns'], row, strict=True)), joints)
             for frame, row in zip(frames, rows, strict=True)}
    depth_order = ('cape', 'thigh_1', 'boot_1', 'thigh_0', 'boot_0', 'torso', 'free_arm',
                   'weapon_arm', 'grip')
    ordered = {name: nodes[name] for name in depth_order if name in nodes}
    return {'parts': parts, 'nodes': ordered, 'poses': poses, 'frames': frames}


def recipe(action, selected=None):
    rows = expanded_rows(action)
    originals = [view for view in RIG['views'] if selected is None or view['id'] in selected]
    active = {view['id'] for view in originals}
    views = [{'id': view['id'], 'offset': list(OFFSET)} for view in originals]
    views.extend({'id': target, 'mirror_of': source}
                 for target, source in RIG['mirrors'].items() if source in active)
    data = {
        'job': {'canvas': [384, 384], 'frame_count': len(rows), 'columns': 4,
                'views': views, 'source_bookends_exact': False,
                'durations_ms': [100] * len(rows), 'require_clear_border': True},
        'scene': {'layers': [{'id': 'art', 'name': 'Body'}],
                  'views': {view['id']: rig_view(view, rows, action) for view in originals}},
    }
    sources = {view['id']: f'character:{RIG["character"]}:{view["id"]}' for view in originals}
    return {'recipe': data, 'sources': sources}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=RIG['clips'])
    parser.add_argument('--views', nargs='+', choices=[row['id'] for row in RIG['views']])
    args = parser.parse_args()
    print(json.dumps(recipe(args.action, args.views), separators=(',', ':')))
