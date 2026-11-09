"""
Realistic bouncing ball animation for Blender (tested on Blender 5.2).

The motion is not hand-keyed: a small physics simulation (gravity, air drag,
spring-damper ground contact, rolling resistance) runs at 1000 Hz and the
result is baked to one keyframe per frame at 60 fps. Contact compression drives
volume-preserving squash, speed drives a subtle stretch, and rotation follows
the distance rolled, so the ball never slides.

Usage:
  GUI:      open Blender > Scripting tab > open this file > Run Script
  Headless: blender -b -P bouncing_ball.py -- [--render-preview]
"""

import math
import os
import sys

import bpy

# ---------------------------------------------------------------- settings
FPS = 60
RADIUS = 0.5            # m
START_HEIGHT = 3.2      # m, height of ball centre at frame 1
START_VX = 1.1          # m/s, forward velocity
GRAVITY = 9.81
RESTITUTION = 0.72      # bounce energy kept (rubber ball ~0.7-0.8)
CONTACT_TIME = 0.045    # s, how long the ball is squashed on the floor
AIR_DRAG = 0.02         # 1/s, gentle linear drag
ROLL_DECEL = 0.35       # m/s^2, rolling resistance while on the floor
CONTACT_FRICTION = 0.06 # fraction of vx lost per bounce
STRETCH_PER_MS = 0.012  # stretch per m/s of vertical speed while airborne
MAX_STRETCH = 1.12
HOLD_SECONDS = 1.0      # still frames at the end
SUBSTEPS = 1000         # physics steps per second


# ---------------------------------------------------------------- simulation
def simulate():
    """Return a list of per-frame (x, z, scale_z, rot_y)."""
    omega = math.pi / CONTACT_TIME
    k = omega * omega                                   # spring, per unit mass
    ln_e = math.log(RESTITUTION)
    zeta = -ln_e / math.sqrt(math.pi ** 2 + ln_e ** 2)  # damping for target e
    c = 2.0 * zeta * omega

    dt = 1.0 / SUBSTEPS
    steps_per_frame = SUBSTEPS // FPS
    x, z, vx, vz = 0.0, START_HEIGHT, START_VX, 0.0
    in_contact = False
    resting = False
    rolled = 0.0
    frames = []
    still_frames = 0
    step = 0

    while True:
        if step % steps_per_frame == 0:
            pen = RADIUS - z
            if pen > 0:
                sz = z / RADIUS                         # squash on contact
            else:
                sz = min(1.0 + STRETCH_PER_MS * abs(vz), MAX_STRETCH, z / RADIUS)
            frames.append((x, z, max(sz, 0.6), rolled / RADIUS))

            if resting and vx == 0.0:
                still_frames += 1
                if still_frames > HOLD_SECONDS * FPS:
                    break
            if len(frames) > 60 * FPS:
                break

        pen = RADIUS - z
        az = -GRAVITY - AIR_DRAG * vz
        ax = -AIR_DRAG * vx
        if pen > 0 or resting:
            if not in_contact:
                in_contact = True
                vx *= 1.0 - CONTACT_FRICTION
            az += max(k * pen - c * vz, 0.0)           # floor never pulls
            if abs(vx) > 0:
                ax -= math.copysign(ROLL_DECEL, vx)
        else:
            in_contact = False

        vz += az * dt
        vx_new = vx + ax * dt
        if vx and vx_new * vx < 0:                      # stop, don't reverse
            vx_new = 0.0
        vx = vx_new

        # settle micro-bounces into a clean rest on the floor
        if resting or (in_contact and abs(vz) < 0.02 and abs(pen) < 0.002):
            resting = True
            vz, z = 0.0, RADIUS

        x += vx * dt
        if not resting:
            z += vz * dt
        rolled += vx * dt
        step += 1

    return frames


# ---------------------------------------------------------------- helpers
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def set_input(node, names, value):
    for n in names if isinstance(names, (list, tuple)) else [names]:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return


def principled(nodes, color, roughness, coat=0.0, spec=0.5):
    p = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(p, "Base Color", (*color, 1.0))
    set_input(p, "Roughness", roughness)
    set_input(p, ["Coat Weight", "Clearcoat"], coat)
    set_input(p, ["Coat Roughness", "Clearcoat Roughness"], 0.08)
    set_input(p, ["Specular IOR Level", "Specular"], spec)
    return p


def ball_material():
    mat = bpy.data.materials.new("RubberBall")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    red = principled(nodes, (0.75, 0.04, 0.03), 0.32, coat=0.6)
    white = principled(nodes, (0.85, 0.83, 0.78), 0.35, coat=0.6)

    # two crossing stripes in object space so the roll is readable
    tc = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    ax = nodes.new("ShaderNodeMath"); ax.operation = "ABSOLUTE"
    az = nodes.new("ShaderNodeMath"); az.operation = "ABSOLUTE"
    mn = nodes.new("ShaderNodeMath"); mn.operation = "MINIMUM"
    lt = nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"
    lt.inputs[1].default_value = 0.07
    mix = nodes.new("ShaderNodeMixShader")

    links.new(tc.outputs["Object"], sep.inputs[0])
    links.new(sep.outputs["X"], ax.inputs[0])
    links.new(sep.outputs["Z"], az.inputs[0])
    links.new(ax.outputs[0], mn.inputs[0])
    links.new(az.outputs[0], mn.inputs[1])
    links.new(mn.outputs[0], lt.inputs[0])
    links.new(lt.outputs[0], mix.inputs[0])
    links.new(red.outputs[0], mix.inputs[1])
    links.new(white.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def simple_material(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    p = nodes.get("Principled BSDF")
    set_input(p, "Base Color", (*color, 1.0))
    set_input(p, "Roughness", roughness)
    set_input(p, ["Specular IOR Level", "Specular"], 0.3)
    return mat


def make_cyclorama(x_min, x_max):
    """Floor that curves up into a back wall: no visible horizon line."""
    profile = []
    for i in range(12):                                   # flat floor
        profile.append((-10.0 + i * (14.0 / 11), 0.0))
    bend_r = 3.0
    for i in range(1, 17):                                # smooth curve
        a = (math.pi / 2) * i / 16
        profile.append((4.0 + bend_r * math.sin(a), bend_r * (1 - math.cos(a))))
    profile.append((4.0 + bend_r, 12.0))                  # wall

    verts, faces = [], []
    xs = [x_min, x_max]
    for x in xs:
        for y, zz in profile:
            verts.append((x, y, zz))
    n = len(profile)
    for j in range(n - 1):
        faces.append((j, j + 1, n + j + 1, n + j))

    mesh = bpy.data.meshes.new("Cyclorama")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Cyclorama", mesh)
    bpy.context.collection.objects.link(obj)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj.data.materials.append(simple_material("Studio", (0.62, 0.63, 0.66), 0.55))
    return obj


def add_area_light(name, loc, rot, energy, size, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------- build
def build():
    clear_scene()
    scene = bpy.context.scene
    frames = simulate()

    # ball: Root carries position + squash (world-aligned),
    # Ball child carries rolling rotation, so squash never tilts.
    root = bpy.data.objects.new("Ball_Root", None)
    root.empty_display_type = "SPHERE"
    root.empty_display_size = RADIUS
    scene.collection.objects.link(root)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=RADIUS)
    ball = bpy.context.active_object
    ball.name = "Ball"
    bpy.ops.object.shade_smooth()
    ball.parent = root
    ball.location = (0, 0, 0)
    ball.data.materials.append(ball_material())

    for i, (x, z, sz, rot) in enumerate(frames):
        f = i + 1
        sxy = 1.0 / math.sqrt(sz)                     # keep volume constant
        # sz == z / RADIUS on contact, so the squashed bottom sits on the floor
        root.location = (x, 0.0, z)
        root.scale = (sxy, sxy, sz)
        ball.rotation_euler = (0.0, rot, 0.0)
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("scale", frame=f)
        ball.keyframe_insert("rotation_euler", frame=f)

    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = len(frames)

    x_end = frames[-1][0]
    make_cyclorama(-20, x_end + 20)

    # camera: low, slightly telephoto, framing the whole run
    mid = x_end / 2
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 50
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = root
    cam_data.dof.aperture_fstop = 4.0
    cam = bpy.data.objects.new("Camera", cam_data)
    dist = max(11.5, x_end * 1.3 + 5.0)
    cam.location = (mid, -dist, 2.3)
    target = bpy.data.objects.new("Cam_Target", None)
    target.location = (mid, 0, 1.85)
    scene.collection.objects.link(target)
    scene.collection.objects.link(cam)
    tc = cam.constraints.new("TRACK_TO")
    tc.target = target
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis = "UP_Y"
    scene.camera = cam

    # three-point studio lighting
    add_area_light("Key", (mid - 4, -4, 6), (math.radians(45), 0, math.radians(-40)), 900, 2.5,
                   (1.0, 0.96, 0.9))
    add_area_light("Fill", (mid + 6, -5, 3), (math.radians(65), 0, math.radians(50)), 250, 6,
                   (0.85, 0.9, 1.0))
    add_area_light("Rim", (mid, 4, 5), (math.radians(-50), 0, 0), 500, 3)

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    bg.inputs[1].default_value = 0.6

    # render settings
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    try:
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = 0.5
    except AttributeError:
        scene.eevee.use_motion_blur = True
    for attr, val in (("use_raytracing", True), ("use_shadows", True),
                      ("taa_render_samples", 64)):
        if hasattr(scene.eevee, attr):
            setattr(scene.eevee, attr, val)
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    if hasattr(scene.render.image_settings, "media_type"):   # Blender 5.0+
        scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    here = os.path.dirname(os.path.abspath(bpy.data.filepath or __file__))
    scene.render.filepath = os.path.join(here, "render", "bouncing_ball_")

    scene.frame_set(1)
    return frames


if __name__ == "__main__":
    frames = build()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    blend_path = os.path.join(out_dir, "bouncing_ball.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"Saved {blend_path}: {len(frames)} frames @ {FPS} fps")

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--render-preview" in argv:
        scene = bpy.context.scene
        if hasattr(scene.render.image_settings, "media_type"):
            scene.render.image_settings.media_type = "IMAGE"
        scene.render.image_settings.file_format = "PNG"
        scene.render.resolution_percentage = 50
        # first impact frame = lowest point of the first fall
        first_hit = min(range(len(frames) // 3), key=lambda i: frames[i][2]) + 1
        for f in (1, first_hit, first_hit + 20):
            scene.frame_set(f)
            scene.render.filepath = os.path.join(out_dir, "preview", f"frame_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
            print("Rendered", scene.render.filepath)
