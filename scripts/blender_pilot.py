#!/usr/bin/env python3
"""Experimental Blender 3D pilot: two stylised Hindi dialogue characters.

Run inside Blender:
  blender -b --python scripts/blender_pilot.py -- \
    --output output/3d_pilot/two_character_preview.mp4 \
    --audio-left output/voice/arjun.wav \
    --audio-right output/voice/meera.wav

This pilot uses amplitude-driven mouth opening only. It is NOT phoneme/viseme Hindi lip sync,
not a production character rig, and not yet connected to the main Wan renderer.
"""
from __future__ import annotations

import argparse
import math
import sys
import wave
from array import array
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/3d_pilot/two_character_preview.mp4")
    parser.add_argument("--audio-left", default="")
    parser.add_argument("--audio-right", default="")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--height", type=int, default=854)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--save-blend", default="")
    return parser.parse_args(raw)


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.72):
    data = bpy.data.materials.new(name=name)
    data.diffuse_color = color
    data.use_nodes = True
    principled = data.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = roughness
    return data


def sphere(name: str, location, scale, mat, segments: int = 32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=20, radius=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    if mat:
        obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return obj


def cylinder(name: str, location, radius: float, depth: float, mat, rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Soft edge bevel", "BEVEL")
    bevel.width = 0.06
    bevel.segments = 3
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def load_amplitude_envelope(path_text: str, frame_count: int, fps: int):
    if not path_text:
        return []
    path = Path(path_text)
    if not path.is_file():
        raise FileNotFoundError(f"Dialogue audio does not exist: {path}")
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        rate = audio.getframerate()
        if channels != 1 or width != 2 or rate != 24000:
            raise ValueError(f"{path} must be 24 kHz mono 16-bit PCM WAV.")
        raw = audio.readframes(audio.getnframes())
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    samples_per_frame = max(1, round(rate / fps))
    levels = []
    for frame in range(frame_count):
        chunk = samples[frame * samples_per_frame:(frame + 1) * samples_per_frame]
        if not chunk:
            levels.append(0.0)
        else:
            energy = sum(float(value) * float(value) for value in chunk) / len(chunk)
            levels.append(math.sqrt(energy) / 32768.0)
    peak = max(levels, default=0.0)
    if peak > 1e-6:
        levels = [min(1.0, value / peak) for value in levels]
    return levels


def animate_mouth(mouth, envelope, frames: int, fps: int, fallback_speaking: bool = False):
    for frame in range(1, frames + 1):
        if envelope:
            amplitude = envelope[frame - 1] if frame - 1 < len(envelope) else 0.0
            # Deliberately exaggerated only enough to prove the driver. This is amplitude,
            # not Hindi phoneme recognition or a final facial animation system.
            opening = 0.025 + 0.13 * (amplitude ** 0.72)
        elif fallback_speaking:
            opening = 0.12 if (frame // max(1, fps // 5)) % 2 else 0.035
        else:
            opening = 0.035
        mouth.scale = (0.115, 0.035, opening)
        mouth.keyframe_insert(data_path="scale", frame=frame)


def add_character(name: str, x: float, skin, shirt, hair, eye, mouth_mat, audio_path: str, frames: int, fps: int, fallback_speaking: bool):
    sphere(f"{name}_body", (x, 0.0, 0.88), (0.54, 0.36, 0.72), shirt)
    cylinder(f"{name}_neck", (x, -0.015, 1.48), 0.17, 0.28, skin)
    head = sphere(f"{name}_head", (x, 0.0, 1.98), (0.44, 0.38, 0.50), skin)
    face_parts = []
    face_parts.append(sphere(f"{name}_hair", (x, 0.035, 2.34), (0.455, 0.39, 0.20), hair))
    face_parts.append(sphere(f"{name}_nose", (x, -0.365, 1.96), (0.075, 0.085, 0.10), skin))
    for side in (-1, 1):
        face_parts.append(sphere(f"{name}_eye_{side}", (x + side * 0.145, -0.34, 2.11), (0.061, 0.035, 0.071), eye))
        face_parts.append(sphere(f"{name}_eye_glint_{side}", (x + side * 0.16, -0.374, 2.135), (0.018, 0.012, 0.02), material(f"{name}_glint_{side}", (1.0, 0.97, 0.88, 1.0), 0.2)))
    mouth = sphere(f"{name}_mouth", (x, -0.375, 1.84), (0.115, 0.035, 0.035), mouth_mat)
    face_parts.append(mouth)
    for part in face_parts:
        part.parent = head
        part.matrix_parent_inverse = head.matrix_world.inverted()
    envelope = load_amplitude_envelope(audio_path, frames, fps) if audio_path else []
    animate_mouth(mouth, envelope, frames, fps, fallback_speaking=fallback_speaking)
    # Small head nod to make the test visibly animated; the rig is intentionally simple.
    head.rotation_euler.x = 0.0
    head.keyframe_insert(data_path="rotation_euler", frame=1)
    head.rotation_euler.x = math.radians(-3)
    head.keyframe_insert(data_path="rotation_euler", frame=max(2, frames // 2))
    head.rotation_euler.x = math.radians(1.5)
    head.keyframe_insert(data_path="rotation_euler", frame=frames)
    return head


def aim_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(name: str, location, power: float, colour, size: float):
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = power
    data.color = colour
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    aim_at(obj, (0, 0, 1.4))
    return obj


def build_scene(args):
    if args.duration <= 0 or args.duration > 8.0:
        raise ValueError("Pilot duration must be >0 and <=8 seconds per qualified shot.")
    if args.fps != 24:
        raise ValueError("The current Wan-aligned pilot baseline is 24 FPS.")
    if args.width <= 0 or args.height <= 0:
        raise ValueError("Output dimensions must be positive.")
    scene = bpy.context.scene
    clear_scene()
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    frames = max(2, math.ceil(args.duration * args.fps))
    scene.frame_start = 1
    scene.frame_end = frames
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.filepath = str(Path(args.output).resolve())
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 48

    # A restrained, warm studio kitchen: stylised shapes, tactile materials and readable faces.
    world = bpy.data.worlds.new("BSK Pilot World") if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.24, 0.27, 0.31, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.38

    skin_a = material("Warm skin A", (0.62, 0.34, 0.22, 1.0))
    skin_b = material("Warm skin B", (0.78, 0.52, 0.36, 1.0))
    shirt_a = material("Muted teal shirt", (0.035, 0.31, 0.34, 1.0))
    shirt_b = material("Terracotta cardigan", (0.48, 0.12, 0.075, 1.0))
    hair_a = material("Dark hair A", (0.035, 0.025, 0.022, 1.0))
    hair_b = material("Dark hair B", (0.07, 0.04, 0.03, 1.0))
    eye_mat = material("Deep brown eyes", (0.018, 0.012, 0.01, 1.0), 0.25)
    mouth_mat = material("Mouth shadow", (0.065, 0.012, 0.018, 1.0), 0.95)
    wall_mat = material("Warm sage wall", (0.19, 0.27, 0.23, 1.0))
    floor_mat = material("Warm stone floor", (0.27, 0.23, 0.19, 1.0))
    table_mat = material("Wood table", (0.21, 0.095, 0.045, 1.0))

    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.02))
    bpy.context.object.name = "Floor"
    bpy.context.object.data.materials.append(floor_mat)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 2.2, 2.7), rotation=(math.radians(90), 0, 0))
    bpy.context.object.name = "Back wall"
    bpy.context.object.data.materials.append(wall_mat)
    cylinder("Small round table", (0, 0.2, 0.57), 0.67, 0.13, table_mat)
    for x in (-0.42, 0.42):
        cylinder(f"Table leg {x}", (x, 0.2, 0.28), 0.045, 0.55, table_mat)

    add_character("Arjun", -0.83, skin_a, shirt_a, hair_a, eye_mat, mouth_mat, args.audio_left, frames, args.fps, not bool(args.audio_left or args.audio_right))
    add_character("Meera", 0.83, skin_b, shirt_b, hair_b, eye_mat, mouth_mat, args.audio_right, frames, args.fps, False)

    bpy.ops.object.camera_add(location=(0, -8.7, 2.65))
    camera = bpy.context.object
    camera.name = "BSK vertical two-shot camera"
    camera.data.lens = 52
    aim_at(camera, (0, 0.0, 1.48))
    scene.camera = camera
    camera.location.x = -0.12
    camera.keyframe_insert(data_path="location", frame=1)
    camera.location.x = 0.12
    camera.keyframe_insert(data_path="location", frame=frames)

    add_area_light("Warm key", (-3.5, -4.2, 6.0), 650, (1.0, 0.78, 0.60), 4.0)
    add_area_light("Soft fill", (3.5, -3.5, 3.8), 320, (0.63, 0.77, 1.0), 4.5)
    add_area_light("Rim light", (0.2, 2.0, 4.7), 500, (1.0, 0.52, 0.30), 3.0)

    scene.view_settings.view_transform = "AgX" if "AgX" in scene.view_settings.bl_rna.properties["view_transform"].enum_items.keys() else scene.view_settings.view_transform
    scene.render.use_file_extension = True
    if args.save_blend:
        blend_path = Path(args.save_blend).resolve()
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(animation=True)
    if not output.is_file() or output.stat().st_size < 50_000:
        raise RuntimeError(f"Blender render did not produce a valid MP4: {output}")
    print(f"BSK_3D_PILOT_COMPLETE output={output} bytes={output.stat().st_size} frames={frames} fps={args.fps}", flush=True)


def main():
    args = parse_args()
    build_scene(args)


if __name__ == "__main__":
    main()
