"""Build the 256 px character atlases from the approved PixelLab artwork."""

import argparse
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
        self.pieces, self.gear, self.gear_center = self.split(image, marks["gear"], underpaint)

    def split(self, image, gear, underpaint):
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
            mask = distance_to_segment(x, y, a, b) <= gear["points"][2][0] ** 2
            center = (a + b) / 2
        gear_image = rgba_layer(source, mask, overlap=0)
        body = source.copy()
        body[mask, 3] = 0
        if underpaint is not None:
            # The original render cannot show the torso and skirt behind the gear.
            # Preserve the visible original and use the clean plate only inside the gear mask.
            paint = np.asarray(underpaint)
            covered = mask & (paint[:, :, 3] > 0)
            body[covered] = paint[covered]
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
        pieces = [Piece(name, start, end, rgba_layer(body, owners == index, overlap=3))
                  for index, (name, start, end) in enumerate(bones)]
        return pieces, gear_image, center

    def pose(self, action, index, row):
        joints = self.joints.copy()
        gait = MOTION["gaits"].get(action)
        gear_turn, gear_pitch = 0, 0
        if action == "idle":
            motion = math.sin(math.tau * index / 8) ** 2 * 1.4
            for name in joints:
                if name.endswith(("foot", "knee", "hip")):
                    continue
                joints[name] -= motion * 1j
        if gait:
            _, lift, _, _ = gait[index % len(gait)]
            torso = self.forward * row["lean"] * 0.72 - lift * 0.22j
            for name in joints:
                if not name.endswith(("foot", "knee")):
                    joints[name] += torso
            for side, phase in zip(SIDES, (0, len(gait) // 2)):
                stride, lift, _, swing = gait[(index + phase) % len(gait)]
                travel = self.forward * stride * (2.8 if action == "run" else 2.2)
                joints[f"{side}_foot"] += travel - lift * 1.65j
                joints[f"{side}_knee"] += travel * 0.52 - lift * 0.54j
                if action != "guard_walk":
                    weight = 0.55 if side == self.gear_side else 1.5
                    joints[f"{side}_elbow"] += self.forward * swing * weight * 0.54
                    joints[f"{side}_hand"] += self.forward * swing * weight - abs(swing) * 0.18j
        hand = joints[self.grip]
        if action in {"guard", "guard_walk", "parry"}:
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
        if action in {"guard", "guard_walk", "parry", "chop", "deflected", "cast"}:
            shoulder_name = f"{self.gear_side}_shoulder"
            elbow_name = f"{self.gear_side}_elbow"
            elbow, shoulder = self.joints[elbow_name], self.joints[shoulder_name]
            upper = abs(elbow - shoulder)
            forearm = abs(self.joints[self.grip] - elbow)
            reach = hand - joints[shoulder_name]
            excess = max(0, abs(reach) - (upper + forearm) * 1.14)
            if excess > 0:
                joints[shoulder_name] += reach / abs(reach) * min(excess, 14)
            joints[elbow_name] += swing * upper / (upper + forearm)
        return joints, gear_turn, gear_pitch

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
        gear = self.transform(self.gear, grip, joints[self.grip],
                              complex(math.cos(turn), math.sin(turn)), math.cos(pitch))
        frame = Image.new("RGBA", (CELL, CELL))
        front = self.gear_side == self.near or self.forward.imag >= 0
        if not front:
            frame.alpha_composite(gear)
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
            frame.alpha_composite(self.transform(piece.image, start, target, factor, axis=end - start))
        if front:
            frame.alpha_composite(gear)
        if action == "cast" and row["cast"] > 0.7:
            self.cast_sparks(frame, joints["left_hand"], row["cast"], index)
        center = (self.gear_center - grip) * complex(math.cos(turn), math.sin(turn))
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


def build(actors, directions, source=SOURCE, destination=ASSETS):
    if len(directions) != len(set(directions)) or any(actor not in RIGS["rigs"] for actor in actors):
        raise ValueError("Unknown actor or repeated direction")
    for actor in actors:
        for direction in directions:
            marks = RIGS["rigs"][actor][direction]
            if (len(marks["joints"]) != len(RIGS["joint_columns"])
                    or any(len(p) != 2 or any(type(v) is not int or not 0 <= v < CELL for v in p)
                           for p in marks["joints"] + marks["gear"]["points"])
                    or marks["gear"]["kind"] not in {"ellipse", "polygon", "segment"}):
                raise ValueError(f"Incomplete rig for {actor} {direction}")
    destination.mkdir(parents=True, exist_ok=True)
    atlas = {"cell_px": CELL, "fps": MOTION["fps"], "origin_px": RIGS["origin_px"],
             "body_height_px": RIGS["body_height_px"], "directions": directions, "clips": []}
    for actor in actors:
        rigs = []
        for direction in directions:
            marks = RIGS["rigs"][actor][direction]
            image = Image.open(source / actor / f"{direction}.png").convert("RGBA")
            if image.size != (CELL, CELL) or not image.getbbox():
                raise ValueError(f"Invalid {actor} {direction} rotation")
            rigs.append(Rig(actor, direction, image, marks, load_underpaint(actor, direction, source)))
        for action, definition in (MOTION["clips"] | RIGS["extra_clips"]).items():
            if actor not in definition["actors"]:
                continue
            motion = motion_rows(action, definition)
            name = f"{actor}-{action}"
            sheet = Image.new("RGBA", (len(motion) * CELL, len(directions) * CELL))
            emitters = []
            for y, rig in enumerate(rigs):
                centers = []
                for x, row in enumerate(motion):
                    frame, emitter = rig.draw(action, x, row)
                    bbox = frame.getchannel("A").getbbox()
                    if bbox is None and (action not in RIGS["extra_clips"] or x != len(motion) - 1):
                        raise ValueError(f"Empty {name} {directions[y]} frame {x}")
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
