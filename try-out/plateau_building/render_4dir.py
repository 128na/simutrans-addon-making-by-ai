"""
四方位対応（BackImage[0]〜[3]に異なる画像）の検証用。
import_and_render.pyと同じカメラ・接地アンカーロジックを使い、
建物をZ軸回転させた4枚(0°/90°/180°/270°)をレンダリングする。
実際にどの回転がゲーム内のどのBackImage[l]スロット・どのマップ方位に対応するかは
理論値でなく実機キャリブレーションで確認する方針(shinkansen_0のvehicle方向較正と同じ)。
出力にはこの後 bake_label.py でZ回転角ラベルを焼き込む。
"""

import bpy
import math
import mathutils
import os
import sys

BASE = os.path.dirname(__file__)
OBJ_PATH = os.path.join(BASE, "source_53394515", "53394515_bldg_6677.obj")

TILE_FIT_MARGIN = 1.05

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
Z_ROTATION_DEG = float(argv[0]) if len(argv) > 0 else 0.0
OUTPUT_NAME = argv[1] if len(argv) > 1 else f"building_4dir_z{int(Z_ROTATION_DEG)}.png"
OUTPUT_PATH = os.path.join(BASE, OUTPUT_NAME)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

bpy.ops.wm.obj_import(filepath=OBJ_PATH, forward_axis='Y', up_axis='Z')
imported = [o for o in bpy.context.selected_objects if o.type == 'MESH']
if len(imported) > 1:
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.join()
    imported = [bpy.context.active_object]
building = imported[0]
bpy.context.view_layer.update()

if Z_ROTATION_DEG:
    building.rotation_euler[2] += math.radians(Z_ROTATION_DEG)
    bpy.context.view_layer.update()

corners = [building.matrix_world @ mathutils.Vector(c) for c in building.bound_box]
xs = [c.x for c in corners]
ys = [c.y for c in corners]
zs = [c.z for c in corners]
center_x = (min(xs) + max(xs)) / 2
center_y = (min(ys) + max(ys)) / 2
min_z = min(zs)
span_x = max(xs) - min(xs)
span_y = max(ys) - min(ys)
span_z = max(zs) - min(zs)
print(f"Z_ROTATION_DEG={Z_ROTATION_DEG} FOOTPRINT_M: x={span_x:.1f} y={span_y:.1f} height={span_z:.1f}")

building.location.x -= center_x
building.location.y -= center_y
building.location.z -= min_z
bpy.context.view_layer.update()

fit_span = max(span_x, span_y, span_z)

cam_data = bpy.data.cameras.new("IsoCam")
cam = bpy.data.objects.new("IsoCam", cam_data)
bpy.context.collection.objects.link(cam)
cam.data.type = 'ORTHO'
cam.data.ortho_scale = fit_span * math.sqrt(2) * TILE_FIT_MARGIN
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

px_per_unit = 128 / cam.data.ortho_scale * math.cos(math.radians(30))
target_z = 32 / px_per_unit

bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, target_z))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
distance = fit_span * 4
cam.location = target - forward * distance
bpy.context.scene.camera = cam

bpy.ops.object.light_add(type='SUN', location=(0, 0, 100))
sun = bpy.context.active_object
sun.data.energy = 3
sun.rotation_euler = (math.radians(45), 0, math.radians(-45))

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = 128
scene.render.resolution_y = 128
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)

img = bpy.data.images.load(OUTPUT_PATH)
w, h = img.size
pixels = list(img.pixels)
for cx, cy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
    i = (cy * w + cx) * 4
    pixels[i:i + 4] = [0.0, 0.0, 0.0, 1.0]
img.pixels[:] = pixels
img.filepath_raw = OUTPUT_PATH
img.file_format = 'PNG'
img.save()
bpy.data.images.remove(img)

print(f"RENDER_DONE: {OUTPUT_PATH}")
