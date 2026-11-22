"""Headless Blender renderer for MONEYSCOPE Shorts (1080x1920, 30 fps).

Run either way:
  blender -b --factory-startup -P pipeline/render.py -- <episode_dir> [--preview]
  python pipeline/render.py <episode_dir> [--preview]        (with `pip install bpy`)

Reads  spec.json, build/timings.json, build/audio_qc.json
Writes build/frames/####.png   (--preview: build/preview/####.png, 1 frame/sec)

Everything is flat emission shading in Cycles so it renders the same on a
CPU-only cloud box and on a laptop.
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
import bmesh

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "ArchivoBlack-Regular.ttf"
FPS = 30
W, H = 1080, 1920
HALF_W, HALF_H = 4.5, 8.0  # scene units (ortho scale 16)

PALETTE = {
    "bg": "#0A1630", "bg2": "#10214A", "grid": "#16295A",
    "green": "#2BD67B", "gold": "#F5B700", "red": "#FF4D4D",
    "white": "#FFFFFF", "dim": "#9FB0D0", "pill": "#050B1A",
}


def lin(hexc):
    hexc = hexc.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(hexc[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def col(name):
    return lin(PALETTE.get(name, name))


# ------------------------------------------------------------------ args
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
EP = Path(argv[0]).resolve()
PREVIEW = "--preview" in argv
spec = json.loads((EP / "spec.json").read_text())
tim = json.loads((EP / "build" / "timings.json").read_text())
qc = json.loads((EP / "build" / "audio_qc.json").read_text())
DURATION = qc["duration"]
NFRAMES = int(math.ceil(DURATION * FPS))
S = tim["sentences"]


def fr(t):
    return int(round(t * FPS)) + 1


# ------------------------------------------------------------------ scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.engine = "CYCLES"
scn.cycles.samples = 12
scn.cycles.use_adaptive_sampling = False
scn.cycles.use_denoising = False
scn.cycles.max_bounces = 0
scn.cycles.transparent_max_bounces = 32
scn.render.use_persistent_data = True   # don't rebuild the scene for every frame
# Several renderer processes can share one frames folder (each skips frames
# another has claimed), which is how run.sh parallelises on multi-core boxes.
scn.render.use_overwrite = False
scn.render.use_placeholder = True
scn.render.film_transparent = False
scn.render.resolution_x, scn.render.resolution_y = W, H
scn.render.resolution_percentage = 100
scn.render.fps = FPS
scn.frame_start, scn.frame_end = 1, NFRAMES
scn.view_settings.view_transform = "Standard"
scn.view_settings.look = "None"
scn.render.image_settings.file_format = "PNG"
scn.render.image_settings.color_mode = "RGB"
scn.render.image_settings.compression = 15
try:  # use the GPU when there is one (Metal on a Mac); CPU in the cloud
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("METAL", "OPTIX", "CUDA", "HIP"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            if any(d.type != "CPU" for d in prefs.devices):
                for d in prefs.devices:
                    d.use = True
                scn.cycles.device = "GPU"
                break
        except Exception:
            continue
except Exception:
    pass
print("cycles device:", scn.cycles.device)

world = bpy.data.worlds.new("w")
scn.world = world
world.color = (0, 0, 0)

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 2 * HALF_H
cam = bpy.data.objects.new("cam", cam_data)
cam.location = (0, 0, 10)
scn.collection.objects.link(cam)
scn.camera = cam

font = bpy.data.fonts.load(str(FONT))

# ------------------------------------------------------------------ helpers
def material(color, name="m"):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = 1.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 1.0
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        pass
    return m, mix.inputs["Fac"]


def link(obj):
    scn.collection.objects.link(obj)
    return obj


def text(body, size, color, x=0.0, y=0.0, z=0.0, align="CENTER", max_w=None, valign="CENTER"):
    cu = bpy.data.curves.new("t", "FONT")
    cu.body = body
    cu.font = font
    cu.size = size
    cu.align_x = align
    cu.align_y = valign
    ob = link(bpy.data.objects.new("t", cu))
    ob.location = (x, y, z)
    m, a = material(col(color) if isinstance(color, str) else color)
    cu.materials.append(m)
    if max_w:
        bpy.context.view_layer.update()
        w = ob.dimensions.x
        if w > max_w:
            f = max_w / w
            ob.scale = (f, f, 1)
    return ob


def rect(w, h, color, x=0.0, y=0.0, z=-0.01, anchor="center"):
    me = bpy.data.meshes.new("r")
    bm = bmesh.new()
    x0 = 0.0 if anchor == "left" else -0.5
    y0 = 0.0 if anchor == "bottom" else -0.5
    vs = [bm.verts.new((x0, y0, 0)), bm.verts.new((x0 + 1, y0, 0)),
          bm.verts.new((x0 + 1, y0 + 1, 0)), bm.verts.new((x0, y0 + 1, 0))]
    bm.faces.new(vs)
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new("r", me))
    ob.location = (x, y, z)
    ob.scale = (w, h, 1)
    m, a = material(col(color) if isinstance(color, str) else color)
    me.materials.append(m)
    return ob


def alpha_key(ob, f, v):
    sock = None
    for m in ob.data.materials:
        for n in m.node_tree.nodes:
            if n.type == "MIX_SHADER":
                sock = n.inputs["Fac"]
    sock.default_value = v
    sock.keyframe_insert("default_value", frame=f)


def render_window(ob, f_in, f_out=None):
    """Keep an object out of the render outside its time window, so stacks
    of invisible layers never eat Cycles' transparency bounces."""
    if f_in > 2:
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=1)
    ob.hide_render = False
    ob.keyframe_insert("hide_render", frame=max(1, f_in - 2))
    if f_out is not None:
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=f_out + 1)


def visible(ob, t_in, t_out=None, fade=0.18, pop=True):
    """Fade (and pop) an object in at t_in, out at t_out."""
    f_in = fr(t_in)
    render_window(ob, f_in, fr(t_out) if t_out is not None else None)
    if t_in <= 0.1:  # frame 1 must already show the hook at full strength
        alpha_key(ob, 1, 1.0)
        if t_out is not None:
            f_out = fr(t_out)
            alpha_key(ob, f_out - int(fade * FPS), 1.0)
            alpha_key(ob, f_out, 0.0)
        return
    alpha_key(ob, max(1, f_in - 1), 0.0)
    alpha_key(ob, f_in + int(fade * FPS), 1.0)
    if pop:
        s = tuple(ob.scale)
        ob.scale = (s[0] * 0.82, s[1] * 0.82, 1)
        ob.keyframe_insert("scale", frame=max(1, f_in - 1))
        ob.scale = (s[0] * 1.04, s[1] * 1.04, 1)
        ob.keyframe_insert("scale", frame=f_in + int(0.16 * FPS))
        ob.scale = s
        ob.keyframe_insert("scale", frame=f_in + int(0.28 * FPS))
    if t_out is not None:
        f_out = fr(t_out)
        alpha_key(ob, f_out - int(fade * FPS), 1.0)
        alpha_key(ob, f_out, 0.0)


def grow_x(ob, t_in, dur=0.6):
    w = ob.scale.x
    ob.scale.x = 0.0001
    ob.keyframe_insert("scale", index=0, frame=fr(t_in))
    ob.scale.x = w
    ob.keyframe_insert("scale", index=0, frame=fr(t_in + dur))


def grow_y(ob, t_in, dur=0.7):
    h = ob.scale.y
    ob.scale.y = 0.0001
    ob.keyframe_insert("scale", index=1, frame=fr(t_in))
    ob.scale.y = h
    ob.keyframe_insert("scale", index=1, frame=fr(t_in + dur))


COUNTERS = []


def counter(ob, t0, dur, to, decimals, prefix, suffix):
    COUNTERS.append((ob, fr(t0), fr(t0 + dur), to, decimals, prefix, suffix))


def fmt_num(v, decimals):
    return f"{v:,.{decimals}f}"


def on_frame(scene, *_):
    f = scene.frame_current
    for ob, f0, f1, to, dec, pre, suf in COUNTERS:
        u = min(1.0, max(0.0, (f - f0) / max(1, f1 - f0)))
        u = 1 - (1 - u) ** 3
        ob.data.body = f"{pre}{fmt_num(to * u, dec)}{suf}"


# ------------------------------------------------------------------ persistent layer
bg = rect(2 * HALF_W + 0.2, 2 * HALF_H + 0.2, "bg", z=-2)
glow = rect(14, 7, "bg2", y=1.0, z=-1.9)
glow.rotation_euler[2] = 0.35
for i in range(-9, 10):
    g = rect(0.025, 40, "grid", x=i * 1.0, z=-1.8)
    g.keyframe_insert("location", frame=1)
    g.location.y = 1.0
    g.keyframe_insert("location", frame=NFRAMES)
for i in range(-12, 13):
    g = rect(20, 0.025, "grid", y=i * 1.0, z=-1.8)
    g.keyframe_insert("location", frame=1)
    g.location.y = i * 1.0 + 1.0
    g.keyframe_insert("location", frame=NFRAMES)
for fc_ob in bpy.data.objects:
    if fc_ob.animation_data and fc_ob.animation_data.action:
        try:
            for fc in fc_ob.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
        except Exception:
            pass

brand = text("MONEYSCOPE", 0.42, "gold", y=7.15, z=0.1)
dot = rect(0.16, 0.16, "green", x=-1.95, y=7.17, z=0.1)
prog_bg = rect(2 * HALF_W, 0.07, "grid", x=-HALF_W, y=7.72, z=0.1, anchor="left")
prog = rect(2 * HALF_W, 0.07, "green", x=-HALF_W, y=7.72, z=0.11, anchor="left")
prog.scale.x = 0.0001
prog.keyframe_insert("scale", index=0, frame=1)
prog.scale.x = 2 * HALF_W
prog.keyframe_insert("scale", index=0, frame=NFRAMES)
for fc in prog.animation_data.action.fcurves if hasattr(prog.animation_data.action, "fcurves") else []:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

# ------------------------------------------------------------------ captions
CAP_Y = -5.55


def caption_chunks(caption, t0, t1, max_chars=24):
    words = caption.split()
    chunks, cur = [], []
    for w in words:
        if cur and len(" ".join(cur + [w])) > max_chars:
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    # never leave a lonely short chunk at the end ("card")
    if len(chunks) > 1 and len(" ".join(chunks[-1])) < 9:
        last = chunks.pop()
        chunks[-1] += last
    total =sum(len(" ".join(c)) + 2 for c in chunks)
    out, t = [], t0
    for c in chunks:
        d = (t1 - t0) * (len(" ".join(c)) + 2) / total
        out.append((" ".join(c), t, t + d))
        t += d
    return out


for i, s in enumerate(spec["sentences"]):
    st = S[i]
    for body, a, z in caption_chunks(s["caption"], st["start"], st["end"]):
        tob = text(body, 0.56, "white", y=CAP_Y, z=0.3, max_w=8.2)
        bpy.context.view_layer.update()
        pw, ph = tob.dimensions.x + 0.55, tob.dimensions.y + 0.42
        pill = rect(pw, ph, "pill", y=CAP_Y, z=0.25)
        for ob in (tob, pill):
            render_window(ob, fr(a), fr(z))
            alpha_key(ob, 1, 0.0)
            alpha_key(ob, max(1, fr(a) - 1), 0.0)
            alpha_key(ob, fr(a), 1.0 if ob is tob else 0.82)
            alpha_key(ob, fr(z) - 1, 1.0 if ob is tob else 0.82)
            alpha_key(ob, fr(z), 0.0)
        for ob in (tob,):
            ob.scale = (ob.scale[0] * 0.92, ob.scale[1] * 0.92, 1)
            ob.keyframe_insert("scale", frame=fr(a))
            ob.scale = (ob.scale[0] / 0.92, ob.scale[1] / 0.92, 1)
            ob.keyframe_insert("scale", frame=fr(a) + 3)

# ------------------------------------------------------------------ scenes
scenes = spec["scenes"]


def scene_window(k):
    t0 = max(0.0, S[scenes[k]["at"]]["start"] - 0.08)
    t1 = S[scenes[k + 1]["at"]]["start"] - 0.08 if k + 1 < len(scenes) else None
    return t0, t1


def tag(body, t0, t1):
    if body:
        ob = text(body, 0.25, "dim", y=-7.25, z=0.2, max_w=8.4)
        visible(ob, t0, t1, pop=False)


for k, sc in enumerate(scenes):
    t0, t1 = scene_window(k)
    typ = sc["type"]
    c = sc.get("color", "white")
    if typ == "big_number":
        lab = text(sc["label"], 0.46, "white", y=3.3, max_w=8.2)
        final = f"{sc.get('prefix','')}{fmt_num(sc['count_to'], sc['decimals'])}{sc.get('suffix','')}"
        num = text(final, 2.3, c, y=1.2, max_w=8.4)
        if t0 > 0.1:  # the frame-1 hook shows its true number immediately
            counter(num, t0 + 0.1, 1.1, sc["count_to"], sc["decimals"], sc.get("prefix", ""), sc.get("suffix", ""))
        bar = rect(5.5, 0.09, c, y=-0.2)
        sub = text(sc.get("sub", ""), 0.5, "dim", y=-0.95, max_w=8.2)
        visible(lab, t0, t1)
        visible(num, t0 + 0.05, t1)
        visible(bar, t0 + 0.2, t1, pop=False)
        grow_x(bar, t0 + 0.2, 0.5)
        visible(sub, t0 + 0.6, t1)
    elif typ in ("statement", "title"):
        lines = sc["lines"]
        size = 1.05 if typ == "statement" else 1.15
        y0 = 1.4 + (len(lines) - 1) * size * 0.62
        if typ == "title":
            badge_t = text(sc["badge"], 0.42, "bg", y=y0 + 1.75, z=0.2, max_w=7.5)
            bpy.context.view_layer.update()
            badge = rect(badge_t.dimensions.x + 0.6, 0.85, c, y=y0 + 1.75, z=0.1)
            visible(badge, t0, t1)
            visible(badge_t, t0, t1)
        for j, ln in enumerate(lines):
            colr = c if (typ == "statement" or j == len(lines) - 1) else "white"
            ob = text(ln, size, colr, y=y0 - j * size * 1.24, max_w=8.4)
            visible(ob, t0 + 0.12 * j + (0.25 if typ == "title" else 0), t1)
    elif typ == "ladder":
        ttl = text(sc["title"], 0.4, "white", y=5.55, max_w=8.4)
        visible(ttl, t0, t1, pop=False)
        maxv = max(r["value"] for r in sc["rows"])
        for j, r in enumerate(sc["rows"]):
            y = 4.0 - j * 2.2
            ta = S[r["reveal_at"]]["start"] - 0.05
            lab = text(r["label"], 0.55, r["color"], x=-4.1, y=y, align="LEFT", max_w=4.5)
            det = text(r["detail"], 0.34, "dim", x=-4.1, y=y - 0.62, align="LEFT", max_w=8.2)
            bar = rect(7.0 * r["value"] / maxv, 0.42, r["color"], x=-4.1, y=y - 1.3, anchor="left")
            val = text(r["value_text"], 0.6, "white", x=4.1, y=y, align="RIGHT", max_w=3.6)
            visible(lab, ta, t1)
            visible(det, ta + 0.1, t1, pop=False)
            visible(bar, ta + 0.05, t1, pop=False)
            grow_x(bar, ta + 0.05, 0.7)
            visible(val, ta + 0.5, t1)
    elif typ == "compare":
        L, R = sc["left"], sc["right"]
        vals = []
        for side, x in ((L, -2.2), (R, 2.2)):
            v = float(side["value"].replace("$", "").replace(",", ""))
            vals.append((side, x, v))
        maxv = max(v for _, _, v in vals)
        for j, (side, x, v) in enumerate(vals):
            ta = t0 + j * 0.9
            h = 5.2 * v / maxv
            bar = rect(2.6, h, side["color"], x=x, y=-3.9, anchor="bottom")
            bar.location.x = x
            valt = text(side["value"], 1.0, side["color"], x=x, y=-3.9 + h + 0.75, max_w=4.0)
            lab = text(side["label"], 0.42, "white", x=x, y=-4.45, max_w=4.0)
            visible(bar, ta, t1, pop=False)
            grow_y(bar, ta, 0.7)
            visible(valt, ta + 0.55, t1)
            visible(lab, ta, t1, pop=False)
    elif typ == "end_card":
        lines = sc["lines"]
        a = text(lines[0], 0.8, "white", y=2.6, max_w=8.0)
        b = text(lines[1], 1.45, "gold", y=1.1, max_w=8.6)
        sub = text(sc.get("sub", ""), 0.45, "dim", y=-0.2, max_w=8.0)
        visible(a, t0, None)
        visible(b, t0 + 0.12, None)
        visible(sub, t0 + 0.3, None)
    tag(sc.get("tag"), t0, t1)

# fix the x-centred bars of compare (anchor bottom is x-centred already)

bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(on_frame)

# ------------------------------------------------------------------ render
out_dir = EP / "build" / ("preview" if PREVIEW else "frames")
out_dir.mkdir(parents=True, exist_ok=True)
if PREVIEW:
    for f in list(range(1, NFRAMES + 1, FPS)) + [NFRAMES]:
        scn.frame_set(f)
        on_frame(scn)
        scn.render.filepath = str(out_dir / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
else:
    scn.render.filepath = str(out_dir) + "/"
    bpy.ops.render.render(animation=True)
print("RENDER DONE", NFRAMES, "frames")
