"""Build the 256 px character atlases from the approved PixelLab artwork."""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
RIGS = json.loads((ROOT / "data/pixellab_motion.json").read_text(encoding="utf-8"))
MOTION = json.loads((ROOT / "data/sprite_motion.json").read_text(encoding="utf-8"))
CELL = RIGS["cell_px"]
ORIGIN = complex(*RIGS["origin_px"])
DIRECTIONS = MOTION["directions"]
SIDES = ("right", "left")
SOURCE = ROOT / "art/pixellab-motion/rotations"
ASSETS = ROOT / "assets/pixellab-sprites"
UNDERPAINT = SOURCE.parent / "underpaint"
GUARD_SHIELD = RIGS["guard_walk_shield"]
GUARD_WALK_FRONT = "guard_walk_front"
PIXEL_NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def distance_to_segment(x, y, start, end):
    vector = end - start
    t = ((x - start.real) * vector.real + (y - start.imag) * vector.imag)
    t = np.clip(t / max(abs(vector) ** 2, 1), 0, 1)
    return (x - start.real - t * vector.real) ** 2 + (y - start.imag - t * vector.imag) ** 2


def rgba_layer(source, mask, overlap=1):
    alpha = Image.fromarray(np.where(mask, source[:, :, 3], 0).astype("uint8"))
    if overlap:
        alpha = alpha.filter(ImageFilter.MaxFilter(2 * overlap + 1))
        alpha = Image.fromarray(np.minimum(np.asarray(alpha), source[:, :, 3]))
    result = Image.fromarray(source.copy())
    result.putalpha(alpha)
    return result


def pixel_regions(mask):
    pixels = set(map(tuple, np.argwhere(mask).tolist()))
    while pixels:
        part = [pixels.pop()]
        for y, x in part:
            for dy, dx in PIXEL_NEIGHBORS:
                nearby = y + dy, x + dx
                if nearby in pixels:
                    pixels.remove(nearby)
                    part.append(nearby)
        yield part


def reassign_fragments(owners, opacity, forearms):
    """Keep loose scraps of cloth attached to the torso or leg they came from."""
    result = owners.copy()
    height, width = owners.shape
    for owner in forearms:
        regions = pixel_regions((owners == owner) & opacity)
        # The largest region is the bone itself. Reconnect smaller fringes at their
        # original seam, leaving intentional isolated details like magic sparks alone.
        for region in sorted(regions, key=len, reverse=True)[1:]:
            neighbors = Counter()
            for y, x in region:
                for dy, dx in PIXEL_NEIGHBORS:
                    py, px = y + dy, x + dx
                    if 0 <= py < height and 0 <= px < width and opacity[py, px]:
                        other = int(owners[py, px])
                        if other not in (owner - 1, owner, *forearms):
                            neighbors[other] += 1
            if neighbors:
                ys, xs = zip(*region)
                result[ys, xs] = neighbors.most_common(1)[0][0]
    return result


def recover_left_arm(image, marks, donor):
    # The front plate has a complete left arm in the same palette and costume.
    # Fit its shoulder and wrist to the new angle, then layer the existing armor on top.
    source, source_marks, outline = donor
    joints = RIGS["joint_columns"]
    shoulder, wrist = joints.index("left_shoulder"), joints.index("left_hand")
    pivot = complex(*source_marks["joints"][shoulder])
    target = complex(*marks["joints"][shoulder])
    original = complex(*source_marks["joints"][wrist]) - pivot
    posed = complex(*marks["joints"][wrist]) - target
    inverse = original / posed
    offset = pivot - inverse * target
    mask = Image.new("1", source.size)
    ImageDraw.Draw(mask).polygon([tuple(point) for point in outline], fill=1)
    arm = rgba_layer(np.asarray(source), np.asarray(mask), overlap=0)
    under = arm.transform(image.size, Image.Transform.AFFINE,
                          (inverse.real, -inverse.imag, offset.real,
                           inverse.imag, inverse.real, offset.imag),
                          resample=Image.Resampling.NEAREST)
    return Image.alpha_composite(under, image)


def close_joint_seam(frame, center, radius, gap):
    """Join close edges at a known joint, retaining the nearest source color."""
    cx, cy = round(center.real), round(center.imag)
    left, top = max(0, cx - radius), max(0, cy - radius)
    right, bottom = min(frame.width, cx + radius + 1), min(frame.height, cy + radius + 1)
    box = left, top, right, bottom
    patch = frame.crop(box)
    alpha = patch.getchannel("A")
    mask = np.asarray(alpha) > 0
    shape = alpha.filter(ImageFilter.MaxFilter(2 * gap + 1)).filter(ImageFilter.MinFilter(2 * gap + 1))
    y, x = np.indices(mask.shape)
    near_joint = (x + left - cx) ** 2 + (y + top - cy) ** 2 <= (radius - gap) ** 2
    missing = np.argwhere((np.asarray(shape) > 0) & ~mask & near_joint)
    if len(missing) == 0:
        return
    original = np.asarray(patch)
    stitched = original.copy()
    solid = np.argwhere(mask)
    for py, px in missing:
        sy, sx = solid[((solid[:, 0] - py) ** 2 + (solid[:, 1] - px) ** 2).argmin()]
        stitched[py, px] = original[sy, sx]
    frame.paste(Image.fromarray(stitched), (left, top))


def clean_pixel_art(frame, keep_magic):
    pixels = np.array(frame)
    rgb = pixels[:, :, :3]
    visible = pixels[:, :, 3] > 0
    for region in pixel_regions(visible):
        if len(region) > 18:
            continue
        y, x = zip(*region)
        colors = rgb[y, x].astype(int)
        if keep_magic and np.any((colors[:, 2] > colors[:, 0] + 12)
                                 & (colors[:, 2] > colors[:, 1] + 22)):
            continue
        pixels[y, x] = 0
        visible[y, x] = False

    # A one-pixel transparent hole shows as a white dot on light backgrounds.
    above = visible[:-2, 1:-1]
    below = visible[2:, 1:-1]
    left = visible[1:-1, :-2]
    right = visible[1:-1, 2:]
    holes = ~visible[1:-1, 1:-1] & above & below & left & right
    for y, x in np.argwhere(holes) + 1:
        neighbors = pixels[[y - 1, y + 1, y, y], [x, x, x - 1, x + 1]]
        pixels[y, x] = neighbors[np.argsort(neighbors[:, :3].sum(axis=1))[1]]
    visible = pixels[:, :, 3] > 0

    # Blend only tiny near-white pinpricks. Broader steel glints stay crisp.
    white = (rgb.min(axis=2) >= 224) & visible
    for region in pixel_regions(white):
        if len(region) > 5:
            continue
        for y, x in region:
            yy, xx = slice(y - 1, y + 2), slice(x - 1, x + 2)
            nearby = rgb[yy, xx][visible[yy, xx] & ~white[yy, xx]]
            if len(nearby) >= 3:
                color = np.median(nearby, axis=0)
                rgb[y, x] = np.rint(rgb[y, x] * .35 + color * .65)
    return Image.fromarray(pixels)


def guard_shield_plates(face_layer, edge_layer):
    width, height = GUARD_SHIELD["size_px"]
    face = face_layer.crop(face_layer.getbbox()).resize((width, height), Image.Resampling.NEAREST)
    edge = edge_layer.crop(edge_layer.getbbox()).resize((round(width * .25), height), Image.Resampling.NEAREST)
    # Keep the shield's real rim, with dark wood on the side that faces its owner.
    wood = ImageOps.colorize(ImageOps.grayscale(face).filter(ImageFilter.GaussianBlur(3)),
                            "#231811", "#72543c")
    wood.putalpha(face.getchannel("A").filter(ImageFilter.MinFilter(15)))
    return face, edge, Image.alpha_composite(face, wood)


@dataclass
class Piece:
    name: str
    start: str
    end: str
    image: Image.Image


class Rig:
    def __init__(self, actor, direction, image, marks, underpaint):
        self.actor = actor
        self.image = image
        self.angle = math.tau * DIRECTIONS.index(direction) / len(DIRECTIONS)
        self.forward = complex(math.sin(self.angle), math.cos(self.angle) * 0.48)
        self.near = "right" if math.sin(self.angle) > 0 else "left"
        self.gear_side = "left" if actor == "hero" else "right"
        self.grip = f"{self.gear_side}_hand"
        self.joints = dict(zip(RIGS["joint_columns"], (complex(*p) for p in marks["joints"]), strict=True))
        self.gear_tip = complex(*marks["gear"]["points"][0])
        feet = [self.joints[f"{side}_foot"] for side in SIDES]
        self.base = complex(sum(p.real for p in feet) / 2, max(p.imag for p in feet) + 2)
        self.scale = RIGS["body_height_px"] / (self.base.imag - self.joints["head"].imag)
        self.offset = ORIGIN - self.base * self.scale
        fringe_joints = marks.get("fringe_joints", ())
        if actor == "ranged":
            fringe_joints = ("right_hand", "left_hand")
        self.pieces, self.gear, self.gear_center = self.split(image, marks["gear"], underpaint, fringe_joints)
        self.guard_shield = None
        self.grip_patch = None
        if actor == "ranged":
            source = np.asarray(image)
            y, x = np.indices(source.shape[:2])
            grip = self.joints[self.grip]
            mask = ((x - grip.real) / 14) ** 2 + ((y - grip.imag) / 6) ** 2 <= 1
            self.grip_patch = rgba_layer(source, mask, overlap=0)

    def split(self, image, gear, underpaint, fringe_joints):
        source = np.asarray(image)
        y, x = np.indices(source.shape[:2])
        a, b = (complex(*p) for p in gear["points"][:2])
        if gear["kind"] == "ellipse":
            mask = ((x - a.real) / b.real) ** 2 + ((y - a.imag) / b.imag) ** 2 <= 1
            center = a
        elif gear["kind"] == "polygon":
            stencil = Image.new("1", image.size)
            ImageDraw.Draw(stencil).polygon([tuple(p) for p in gear["points"]], fill=1)
            mask = np.asarray(stencil)
            center = sum(complex(*p) for p in gear["points"]) / len(gear["points"])
        else:
            radius = gear["points"][2][0]
            if self.actor == "ranged":
                radius = radius + 6 * (y < a.imag + 39)
            mask = distance_to_segment(x, y, a, b) <= radius ** 2
            center = (a + b) / 2
        gear_image = rgba_layer(source, mask, overlap=0)
        if self.actor == "ranged" and gear["kind"] == "segment":
            # Keep thin wood continuous where the source's shaft has a pixel-wide notch.
            for i in range(6, 16):
                close_joint_seam(gear_image, a + (b - a) * (i / 16), radius=11, gap=2)
        body = source.copy()
        body[mask, 3] = 0
        if underpaint is not None:
            # The original render cannot show the torso and skirt behind the gear.
            # Preserve the visible original and use the clean plate only inside the gear mask.
            paint = np.asarray(underpaint)
            covered = mask & (paint[:, :, 3] > 0)
            body[covered] = paint[covered]
        if self.actor == "hero":
            hips = (self.joints["left_hip"] + self.joints["right_hip"]) / 2
            trunk = distance_to_segment(x, y, self.joints["neck"], hips) < 26 ** 2
            self.guard_torso = rgba_layer(body, trunk, overlap=0)
        bones = [("head", "head", "neck"), ("body", "neck", "waist")]
        for side in SIDES:
            for start, end in (("shoulder", "elbow"), ("elbow", "hand"),
                               ("hip", "knee"), ("knee", "foot")):
                bones.append((f"{side}_{end}", f"{side}_{start}", f"{side}_{end}"))
        scores = []
        for name, start, end in bones:
            distance = distance_to_segment(x, y, self.joints[start], self.joints[end])
            # A wide torso and hanging skirt stay joined to the waist when a foot swings.
            if name == "body":
                distance *= 0.66
            scores.append(distance)
        owners = np.argmin(scores, axis=0)
        opaque = body[:, :, 3] > 0
        if self.actor == "ranged":
            red, green, blue = (body[:, :, channel].astype(int) for channel in range(3))
            # The robe hangs from the belt and should not peel away with a shin.
            cloth = ((y > self.joints["waist"].imag + 7)
                     & (red > green + 5) & (blue >= green * .93) & (green < 95))
            for side in SIDES:
                foot = self.joints[f"{side}_foot"]
                # Preserve the boots below the hem, including their dark outlines.
                footwear = (y > foot.imag - 26) & (abs(x - foot.real) < 22)
                cloth &= ~footwear
            owners[cloth & opaque] = 1
        forearms = [i for i, (name, _, _) in enumerate(bones) if name in fringe_joints]
        owners = reassign_fragments(owners, opaque, forearms)
        pieces = [Piece(name, start, end, rgba_layer(body, owners == index, overlap=3))
                  for index, (name, start, end) in enumerate(bones)]
        if self.actor == "hero":
            self.guard_arm = {}
            for piece in pieces:
                if piece.name not in ("left_elbow", "left_hand"):
                    continue
                limb = distance_to_segment(x, y, self.joints[piece.start], self.joints[piece.end])
                radius = 18 if piece.name == "left_elbow" else 15
                self.guard_arm[piece.name] = rgba_layer(np.asarray(piece.image), limb <= radius ** 2, overlap=0)
        return pieces, gear_image, center

    def set_guard_shield(self, plates):
        face, edge, back = plates
        sideways = math.cos(self.angle)
        if abs(sideways) < 1e-9:
            profile = ImageOps.mirror(edge) if self.forward.real > 0 else edge
            shield = Image.new("RGBA", (CELL, CELL))
            shield.paste(profile, (round(ORIGIN.real - profile.width / 2),
                                  round(ORIGIN.imag - profile.height / 2)))
        else:
            plate = face if sideways > 0 else back
            # Project the upright disc across the direction the torso is facing.
            scale = abs(sideways)
            shear = -.28 * math.sin(self.angle) / sideways
            shield = plate.transform((CELL, CELL), Image.Transform.AFFINE,
                                     (1 / scale, 0, plate.width / 2 - ORIGIN.real / scale,
                                      -shear, 1, plate.height / 2 - ORIGIN.imag + shear * ORIGIN.real),
                                     resample=Image.Resampling.NEAREST)
        self.guard_shield = shield

    def pose(self, action, index, row):
        joints = self.joints.copy()
        gait_action = GUARD_SHIELD["base_action"] if action == GUARD_WALK_FRONT else action
        gait = MOTION["gaits"].get(gait_action)
        gear_turn, gear_pitch = 0, 0
        if action == "idle":
            motion = math.sin(math.tau * index / 8) ** 2 * 1.4
            for name in joints:
                if name.endswith(("foot", "knee", "hip")):
                    continue
                joints[name] -= motion * 1j
        if gait:
            _, lift, _, _ = gait[index % len(gait)]
            running = action == "run"
            if running:
                opposite_lift = gait[(index + len(gait) // 2) % len(gait)][1]
                torso = self.forward * row["lean"] * 0.42 - min(lift, opposite_lift) * 0.62j
                tilt = self.forward * row["lean"] * 0.68
            else:
                torso = self.forward * row["lean"] * 0.72 - lift * 0.22j
                tilt = 0
            for name in joints:
                if name.endswith(("foot", "knee")):
                    continue
                joints[name] += torso
                if name != "waist" and not name.endswith("hip"):
                    joints[name] += tilt
            joints["head"] += tilt * 0.29
            stride_scale = {"run": 2.15, "guard_walk": 2.8}.get(gait_action, 2.2)
            feet_center = (self.joints["right_foot"] + self.joints["left_foot"]) / 2
            for side, phase in zip(SIDES, (0, len(gait) // 2)):
                stride, lift, _, swing = gait[(index + phase) % len(gait)]
                travel = self.forward * stride * stride_scale
                foot, knee = f"{side}_foot", f"{side}_knee"
                if running:
                    stance = (self.joints[foot] - feet_center) / self.forward
                    tuck = self.forward * complex(stance.real * .43, stance.imag * .12)
                    joints[foot] -= tuck
                    joints[knee] -= tuck * .55
                joints[foot] += travel - lift * 1.65j
                joints[knee] += travel * 0.52 - lift * (0.75 if running else 0.54) * 1j
                if gait_action != "guard_walk" or side != self.gear_side:
                    weight = 1.5
                    if side == self.gear_side:
                        weight = 0.36 if running else 0.55
                    joints[f"{side}_elbow"] += self.forward * swing * weight * 0.54
                    joints[f"{side}_hand"] += self.forward * swing * weight - abs(swing) * 0.18j
                    if running and side != self.gear_side:
                        joints[f"{side}_elbow"] -= max(0, swing) * 0.21j
                        joints[f"{side}_hand"] -= max(0, swing) * 0.63j
        if action == "stagger":
            gear_turn, gear_pitch = self.stagger(joints, row)
        hand = joints[self.grip]
        if action == GUARD_WALK_FRONT:
            cross = complex(math.cos(self.angle), -.48 * math.sin(self.angle))
            neck, waist = joints["neck"], joints["waist"]
            chest = neck + (waist - neck) * GUARD_SHIELD["chest_ratio"]
            reach = (row["shield_forward"] - 5) * GUARD_SHIELD["depth_scale"]
            hand = chest + self.forward * reach + cross * GUARD_SHIELD["left_bias_px"]
            hand -= (row["shield_up"] - 12) * 1.64j
        elif action in {"guard", "guard_walk", "parry"}:
            guard = self.forward * (row["shield_forward"] - 5) * 1.35
            rise = (row["shield_up"] - 1) * (2.08 if action == "parry" else 1.64)
            hand += guard - rise * 1j
            # The shield's local up axis foreshortens as its face tilts towards the sky.
            gear_pitch = math.radians(row.get("shield_pitch_deg", 0))
            gear_turn = math.sin(self.angle) * gear_pitch * 0.52
        elif action in {"chop", "deflected"}:
            drive = self.forward * (row["blade_forward"] - 6) * 1.72
            hand += drive - (row["blade_up"] - 4) * 1.6j
            if action == "deflected":
                hand -= self.forward * row["retreat"] * 0.5
                step = self.forward * row["retreat"] * 1.35
                for side, factor in zip(SIDES, (1.0, 0.55)):
                    joints[f"{side}_foot"] -= step * factor + 1j * abs(row["stride"]) * 0.42
                    joints[f"{side}_knee"] -= step * factor * 0.51
            blade = self.gear_tip - self.joints[self.grip]
            elevation = math.radians(row["blade_angle"])
            projected = self.forward * math.cos(elevation) - 1j * math.sin(elevation)
            attack_weight = min(1, abs(row["blade_angle"] - 61) / 42)
            aimed = blade / abs(blade) * (1 - attack_weight) + projected * attack_weight
            turn = aimed / blade
            gear_turn = math.atan2(turn.imag, turn.real)
        elif action == "cast":
            hand += self.forward * (row["blade_forward"] - 6) * 1.7 - (row["blade_up"] - 4) * 1.45j
            joints["left_hand"] += self.forward * row["cast"] * 5.4 - row["cast"] * 3.1j
            joints["left_elbow"] += self.forward * row["cast"] * 2.7
            gear_turn = (1 if self.forward.real >= 0 else -1) * (row["blade_angle"] - 61) * 0.016
        joints[self.grip] = hand
        swing = hand - self.joints[self.grip]
        if action in {"guard", "guard_walk", GUARD_WALK_FRONT, "parry", "chop", "deflected", "cast"}:
            shoulder_name = f"{self.gear_side}_shoulder"
            elbow_name = f"{self.gear_side}_elbow"
            elbow, shoulder = self.joints[elbow_name], self.joints[shoulder_name]
            upper = abs(elbow - shoulder)
            forearm = abs(self.joints[self.grip] - elbow)
            reach = hand - joints[shoulder_name]
            excess = max(0, abs(reach) - (upper + forearm) * 1.14)
            if excess > 0 and action != GUARD_WALK_FRONT:
                joints[shoulder_name] += reach / abs(reach) * min(excess, 14)
            if action == GUARD_WALK_FRONT:
                # Keep the upper arm anchored to the shoulder while the forearm crosses the chest.
                forearm_shift = hand - (self.joints[self.grip] + joints["neck"] - self.joints["neck"])
                joints[elbow_name] += forearm_shift * min(.42, 15 / max(1, abs(forearm_shift)))
            else:
                joints[elbow_name] += swing * upper / (upper + forearm)
        return joints, gear_turn, gear_pitch

    def stagger(self, joints, row):
        lean = self.forward * row["lean"]
        dip = row["crouch"] * .7j
        for name in joints:
            if not name.endswith(("knee", "foot")):
                amount = .36 if name == "waist" or name.endswith("hip") else 1.0
                joints[name] += lean * amount + dip
        joints["head"] += lean * .2
        for side, sign in zip(SIDES, (-1, 1)):
            stepping = max(0, sign * row["stride"])
            step = -self.forward * (row["retreat"] * .45 + stepping * 1.2)
            lift = min(1, stepping / 8) * row["knee"]
            joints[f"{side}_foot"] += step - lift * 1j
            joints[f"{side}_knee"] += step * .48 - lift * .36j + dip * .37
        # The staff follows the right wrist; the free hand catches the balance.
        raise_staff = (row["blade_up"] - 4) * 1.23j
        joints["right_elbow"] -= raise_staff * .47
        joints["right_hand"] += self.forward * (row["blade_forward"] - 6) - raise_staff
        joints["left_hand"] -= lean * .53 + abs(row["lean"]) * .65j
        joints["left_elbow"] -= lean * .21 + abs(row["lean"]) * .22j
        pitch = math.radians(row["blade_angle"] - 61)
        return -math.sin(self.angle) * pitch, abs(math.cos(self.angle)) * pitch

    def transform(self, image, start, target, factor=1, vertical=1, opacity=1, axis=None):
        inverse = 1 / (self.scale * factor)
        target = self.offset + target * self.scale
        a, b = inverse.real, inverse.imag
        xx, xy, yx, yy = a, -b, b / vertical, a / vertical
        if axis is not None:
            # Stretch a limb along the bone and preserve the thickness of its texture.
            parallel = axis / abs(axis)
            amount = abs(factor) - 1
            normal_x = parallel.real
            normal_y = parallel.imag
            m11 = 1 + amount * normal_y ** 2
            m12 = -amount * normal_x * normal_y
            m22 = 1 + amount * normal_x ** 2
            xx, xy, yx, yy = (m11 * xx + m12 * yx, m11 * xy + m12 * yy,
                              m12 * xx + m22 * yx, m12 * xy + m22 * yy)
        result = image.transform((CELL, CELL), Image.Transform.AFFINE,
                                 (xx, xy, start.real - xx * target.real - xy * target.imag,
                                  yx, yy, start.imag - yx * target.real - yy * target.imag),
                                 resample=Image.Resampling.NEAREST)
        if opacity < 1:
            result.putalpha(result.getchannel("A").point(lambda value: round(value * opacity)))
        return result

    def draw(self, action, index, row):
        if action == "ash":
            return self.ash(index), ORIGIN
        if action == "collapse":
            return self.collapse(index), ORIGIN
        if action == "idle" and index == 0:
            return self.transform(self.image, self.base, self.base), self.offset + self.gear_center * self.scale
        joints, turn, pitch = self.pose(action, index, row)
        grip = self.joints[self.grip]
        frame = Image.new("RGBA", (CELL, CELL))
        if action == GUARD_WALK_FRONT:
            gear = self.transform(self.guard_shield, ORIGIN, joints[self.grip])
            front = self.forward.imag >= -1e-9
            center = 0j
        else:
            rotation = complex(math.cos(turn), math.sin(turn))
            gear = self.transform(self.gear, grip, joints[self.grip], rotation, math.cos(pitch))
            front = self.gear_side == self.near or self.forward.imag >= 0
            center = (self.gear_center - grip) * rotation
        grip_patch = None
        if self.grip_patch is not None:
            grip_patch = self.transform(self.grip_patch, grip, joints[self.grip])
        if not front:
            frame.alpha_composite(gear)
            if grip_patch is not None:
                frame.alpha_composite(grip_patch)
        if action == GUARD_WALK_FRONT:
            frame.alpha_composite(self.transform(self.guard_torso, self.joints["neck"], joints["neck"]))
        order = ("foot", "knee", "hand", "elbow")
        pieces = sorted(self.pieces, key=lambda p: (6 if p.name == "head" else
                        3 if p.name == "body" else order.index(p.name.split("_")[1]) +
                        (2 if p.name.startswith(self.near) else 0)))
        for piece in pieces:
            start, end = self.joints[piece.start], self.joints[piece.end]
            target, tip = joints[piece.start], joints[piece.end]
            factor = (tip - target) / (end - start)
            if abs(factor) < 0.24:
                factor = 0.24
            image = self.guard_arm.get(piece.name, piece.image) if action == GUARD_WALK_FRONT else piece.image
            frame.alpha_composite(self.transform(image, start, target, factor, axis=end - start))
        if front:
            frame.alpha_composite(gear)
            if grip_patch is not None:
                frame.alpha_composite(grip_patch)
        if self.actor == "ranged":
            arm = joints["right_elbow"] * .24 + joints[self.grip] * .76
            close_joint_seam(frame, self.offset + arm * self.scale, radius=16, gap=3)
            for side in SIDES:
                ankle = joints[f"{side}_knee"] * .34 + joints[f"{side}_foot"] * .66
                close_joint_seam(frame, self.offset + ankle * self.scale, radius=15, gap=3)
        if action == "cast" and row["cast"] > 0.7:
            self.cast_sparks(frame, joints["left_hand"], row["cast"], index)
        emitter = self.offset + (joints[self.grip] + complex(center.real, center.imag * math.cos(pitch))) * self.scale
        return frame, emitter

    def cast_sparks(self, frame, palm, power, index):
        center = self.offset + (palm + self.forward * 6 - 12j) * self.scale
        draw = ImageDraw.Draw(frame)
        colors = ("#82588f", "#b87dda", "#e9c6ff")
        for i in range(8):
            angle = math.tau * (i / 8 + index / 24)
            radius = (2 + (i % 3) * 2) * power
            point = center + complex(math.cos(angle), math.sin(angle)) * radius
            r = 1 + (i % 2)
            x, y = round(point.real), round(point.imag)
            draw.rectangle((x - r, y - r, x + r, y + r), fill=colors[i % len(colors)])

    def collapse(self, index):
        frame = Image.new("RGBA", (CELL, CELL))
        if index == 0:
            return self.transform(self.image, self.base, self.base)
        time = index / 15
        settle = min(1, time * 2)
        fade = min(1, (1 - time) * 3.5)
        for number, piece in enumerate([*self.pieces, Piece("weapon", self.grip, self.grip, self.gear)]):
            pivot = self.joints[piece.start]
            spread = (-1 if number % 2 else 1) * (14 + (number * 17) % 45)
            ground = self.base.imag - 11 + (number * 3) % 16
            drop = (ground - pivot.imag) * settle ** 2
            rotation = settle * spread * 0.044
            factor = complex(math.cos(rotation), math.sin(rotation))
            vertical = max(0.26, 1 - settle * 0.7)
            bounds = piece.image.getchannel("A").getbbox()
            if bounds is None:
                continue
            left, top, right, bottom = bounds
            floor = max(((complex(x - pivot.real, (y - pivot.imag) * vertical) * factor).imag)
                        for x in (left, right) for y in (top, bottom))
            max_drop = (CELL - 5 - self.offset.imag) / self.scale - pivot.imag - floor
            frame.alpha_composite(self.transform(
                piece.image, pivot, pivot + complex(spread * settle, min(drop, max_drop)),
                factor, vertical, fade,
            ))
        return frame


    def ash(self, index):
        original = self.transform(self.image, self.base, self.base)
        frame = Image.new("RGBA", (CELL, CELL))
        if index == 0:
            return original
        time = index / 15
        rng = random.Random(312)
        step = 3
        draw = ImageDraw.Draw(frame)
        for y in range(step, CELL - step, step):
            for x in range(step, CELL - step, step):
                red, green, blue, alpha = original.getpixel((x, y))
                if alpha == 0:
                    continue
                burn = np.clip((y - 0.65 * CELL) / CELL + 0.46 + rng.uniform(0, 0.54), 0.07, 0.88)
                scatter, drift, wind = rng.random(), rng.random(), rng.random()
                if burn > time:
                    tile = original.crop((x - 1, y - 1, x + 2, y + 2))
                    frame.paste(tile, (x - 1, y - 1))
                elif scatter < 0.49:
                    age = (time - burn) / (1 - burn)
                    dust_x = x + (drift - 0.53) * age * 86 + self.forward.real * age * 19
                    dust_y = y - age * min(y - 2, 18 + wind * 50)
                    gray = (red + green + blue) // 3
                    color = (gray + 13, gray + 8, gray + 2, round(alpha * (1 - age) ** 2.0))
                    if max(color[:3]) > 255:
                        color = tuple(min(255, v) for v in color)
                    draw.rectangle((dust_x, dust_y, dust_x + 1, dust_y + 1), fill=color)
        return frame


def load_underpaint(actor, direction, source):
    row = RIGS["underpaint"].get(actor, {}).get(direction)
    if row is None:
        return None
    paint = Image.new("RGBA", (CELL, CELL))
    if "file" in row:
        image = Image.open(UNDERPAINT / row["file"]).convert("RGBA")
        if image.size != paint.size:
            raise ValueError(f"Wrong underpaint size for {actor}/{direction}")
        if row["mirror"]:
            image = ImageOps.mirror(image)
        paint.paste(image, tuple(row["offset"]))
    else:
        left, top, right, bottom = row["bounds"]
        image = Image.open(source / actor / f'{row["direction"]}.png').convert("RGBA")
        patch = image.crop(row["box"]).resize((right - left, bottom - top), Image.Resampling.NEAREST)
        paint.paste(patch, (left, top))
    return paint


def motion_rows(action, definition):
    if action in RIGS["extra_clips"]:
        return [{}] * definition["count"]
    frames = [dict(zip(MOTION["motion_columns"], row, strict=True)) for row in definition["frames"]]
    pitches = definition.get("shield_pitch_deg", [0] * len(frames))
    for frame, pitch in zip(frames, pitches, strict=True):
        frame["shield_pitch_deg"] = pitch
    count = len(MOTION["gaits"][action]) if action in MOTION["gaits"] else (
        8 if action == "idle" else frames[-1]["frame"] + int(not definition["loop"])
    )
    rows = []
    for index in range(count):
        a, b = next(((a, b) for a, b in zip(frames, frames[1:]) if b["frame"] >= index),
                    (frames[-1], frames[-1]))
        fraction = (index - a["frame"]) / max(1, b["frame"] - a["frame"])
        rows.append({key: value + (b[key] - value) * fraction for key, value in a.items()})
    return rows


def load_rig(actor, direction, source, donor):
    marks = RIGS["rigs"][actor][direction]
    image = Image.open(source / actor / f"{direction}.png").convert("RGBA")
    if image.size != (CELL, CELL) or not image.getbbox():
        raise ValueError(f"Invalid {actor} {direction} rotation")
    if marks.get("restore_left_arm"):
        if actor != RIGS["left_arm_patch"]["actor"] or donor is None:
            raise ValueError(f"No matching left arm plate for {actor} {direction}")
        image = recover_left_arm(image, marks, donor)
    image = clean_pixel_art(image, keep_magic=actor == "ranged")
    return Rig(actor, direction, image, marks, load_underpaint(actor, direction, source))


def build(actors, directions, source=SOURCE, destination=ASSETS):
    if len(directions) != len(set(directions)) or any(actor not in RIGS["rigs"] for actor in actors):
        raise ValueError("Unknown actor or repeated direction")
    shield_sources = [GUARD_SHIELD["face_direction"], GUARD_SHIELD["edge_direction"]]
    shield_size = GUARD_SHIELD["size_px"]
    guard_base = GUARD_SHIELD["base_action"]
    if (guard_base not in MOTION["gaits"] or guard_base not in MOTION["clips"]
            or MOTION["clips"][guard_base]["actors"] != ["hero"]
            or any(direction not in DIRECTIONS for direction in shield_sources)
            or len(shield_size) != 2 or any(type(size) is not int or not 0 < size < CELL for size in shield_size)
            or not 0 < GUARD_SHIELD["chest_ratio"] < 1
            or any(not 0 < GUARD_SHIELD[key] < CELL for key in ("depth_scale", "left_bias_px"))):
        raise ValueError("Invalid walking shield rig")
    for actor in actors:
        for direction in directions:
            marks = RIGS["rigs"][actor][direction]
            if (len(marks["joints"]) != len(RIGS["joint_columns"])
                    or any(len(p) != 2 or any(type(v) is not int or not 0 <= v < CELL for v in p)
                           for p in marks["joints"] + marks["gear"]["points"])
                    or any(name not in RIGS["joint_columns"] for name in marks.get("fringe_joints", ()))
                    or marks["gear"]["kind"] not in {"ellipse", "polygon", "segment"}):
                raise ValueError(f"Incomplete rig for {actor} {direction}")
    donor_spec = RIGS["left_arm_patch"]
    donor_actor, donor_direction = donor_spec["actor"], donor_spec["direction"]
    donor = None
    if donor_actor in actors:
        image = Image.open(source / donor_actor / f"{donor_direction}.png").convert("RGBA")
        outline = donor_spec["outline"]
        if image.size != (CELL, CELL) or len(outline) < 3 or any(
            len(p) != 2 or any(type(v) is not int or not 0 <= v < CELL for v in p) for p in outline
        ):
            raise ValueError("Invalid left arm plate")
        donor = image, RIGS["rigs"][donor_actor][donor_direction], outline
    destination.mkdir(parents=True, exist_ok=True)
    atlas = {"cell_px": CELL, "fps": MOTION["fps"], "origin_px": RIGS["origin_px"],
             "body_height_px": RIGS["body_height_px"], "directions": directions, "clips": []}
    clips = MOTION["clips"] | {GUARD_WALK_FRONT: MOTION["clips"][guard_base]} | RIGS["extra_clips"]
    for actor in actors:
        required = list(dict.fromkeys([*directions, *shield_sources])) if actor == "hero" else directions
        rigs = {direction: load_rig(actor, direction, source, donor) for direction in required}
        if actor == "hero":
            plates = guard_shield_plates(*(rigs[direction].gear for direction in shield_sources))
            for rig in rigs.values():
                rig.set_guard_shield(plates)
        for action, definition in clips.items():
            if actor not in definition["actors"]:
                continue
            motion = motion_rows(guard_base if action == GUARD_WALK_FRONT else action, definition)
            name = f"{actor}-{action}"
            sheet = Image.new("RGBA", (len(motion) * CELL, len(directions) * CELL))
            emitters = []
            for y, direction in enumerate(directions):
                rig = rigs[direction]
                centers = []
                for x, row in enumerate(motion):
                    frame, emitter = rig.draw(action, x, row)
                    if action not in RIGS["extra_clips"]:
                        frame = clean_pixel_art(frame, keep_magic=actor == "ranged")
                    bbox = frame.getchannel("A").getbbox()
                    if bbox is None and (action not in RIGS["extra_clips"] or x != len(motion) - 1):
                        raise ValueError(f"Empty {name} {directions[y]} frame {x}")
                    if bbox and (min(bbox[:2]) <= 0 or max(bbox[2:]) >= CELL):
                        raise ValueError(f"Clipped {name} {directions[y]} frame {x}")
                    if actor == "hero" and action in {"run", "guard_walk", GUARD_WALK_FRONT}:
                        regions = sorted(map(len, pixel_regions(np.asarray(frame.getchannel("A")) > 0)),
                                         reverse=True)
                        if len(regions) > 1 and regions[1] >= 36:
                            raise ValueError(f"Separated limb in {name} {directions[y]} frame {x}")
                    sheet.paste(frame, (x * CELL, y * CELL))
                    centers.append([round(emitter.real), round(emitter.imag)])
                emitters.append(centers)
            sheet.save(destination / f"{name}.png")
            flash = Image.new("RGBA", sheet.size, "white")
            flash.putalpha(sheet.getchannel("A"))
            flash.save(destination / f"{name}-flash.png")
            clip = {"actor": actor, "action": action, "frames": len(motion),
                    "loop": definition["loop"], "file": f"{name}.png"}
            if actor == "hero":
                clip["shield_px"] = emitters
            atlas["clips"].append(clip)
            print(f"{name}: {len(motion)} frames x {len(directions)} directions", flush=True)
    (destination / "atlas.json").write_text(json.dumps(atlas, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actors", nargs="+", default=MOTION["actors"])
    parser.add_argument("--directions", nargs="+", choices=DIRECTIONS, default=DIRECTIONS)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=ASSETS)
    args = parser.parse_args()
    build(args.actors, args.directions, args.source, args.output)
