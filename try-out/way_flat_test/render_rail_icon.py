"""
pak128 線路用アイコン/カーソル画像レンダリング
出力: 512x512px RGB PNG（"_raw"、postprocess.pyで128x128に変換してcursor/icon用にする）
"""

import bpy
import math
import mathutils
import os

SUPERSAMPLE = 4
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "rail_icon_raw.png")

# render_rail.pyと同じpxベースの寸法・変換係数（詳細はそちらのコメント参照）
PX_PER_BU_Z = (128 / math.sqrt(2)) * math.cos(math.radians(30))
PX_PER_BU_HORIZ = 128 / 2
BALLAST_HEIGHT_PX = 1.0
RAIL_HEIGHT_PX = 1.0
RAIL_GAUGE_PX = 10.0

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# render_rail.pyと同じ（詳細はそちらのコメント参照）: 2px差を道床の小さな段差(1px)と
# 奥レールのXシフト(1px)に半分ずつ分割する折衷案
BALLAST_WIDTH = 0.65
NEAR_BALLAST_DOWN_PX = 1.0
FAR_BALLAST_STEP_PX = 1.0
FAR_RAIL_X_SHIFT_PX = 1.0
PX_PER_BU_HORIZ_TO_DY = 32.0

ballast_h = BALLAST_HEIGHT_PX / PX_PER_BU_Z
ballast_mat = bpy.data.materials.new(name="BallastIconMat")
ballast_mat.use_nodes = True
bsdf = ballast_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.40, 0.36, 0.30, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.40, 0.36, 0.30, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.2

ballast_halves = [
    (BALLAST_WIDTH / 4, NEAR_BALLAST_DOWN_PX),
    (-BALLAST_WIDTH / 4, NEAR_BALLAST_DOWN_PX + FAR_BALLAST_STEP_PX),
]
for x_center, down_px in ballast_halves:
    z = ballast_h / 2 - (down_px / PX_PER_BU_Z)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x_center, 0, z))
    ballast = bpy.context.active_object
    ballast.scale = (BALLAST_WIDTH / 2, 1.0, ballast_h)
    ballast.data.materials.append(ballast_mat)

rail_h = RAIL_HEIGHT_PX / PX_PER_BU_Z
rail_mat = bpy.data.materials.new(name="RailIconMat")
rail_mat.use_nodes = True
bsdf = rail_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.14, 0.14, 0.16, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.30, 0.30, 0.33, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.15

rail_gauge_bu = RAIL_GAUGE_PX / PX_PER_BU_HORIZ

rails = [
    (-rail_gauge_bu / 2 + FAR_RAIL_X_SHIFT_PX / PX_PER_BU_HORIZ_TO_DY,
     NEAR_BALLAST_DOWN_PX + FAR_BALLAST_STEP_PX),
    (rail_gauge_bu / 2, NEAR_BALLAST_DOWN_PX),
]
for offset_x, down_px in rails:
    z = ballast_h + rail_h / 2 - (down_px / PX_PER_BU_Z)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(offset_x, 0, z))
    rail = bpy.context.active_object
    rail.scale = (0.02, 1.0, rail_h)
    rail.data.materials.append(rail_mat)

bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 1.9  # アイコンは余白を持たせて全体が収まるように
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
GROUND_ANCHOR_Z = 0.408  # render_rail.pyと同じ固定アンカー（詳細はそちらのコメント参照）
target = mathutils.Vector((0, 0, GROUND_ANCHOR_Z))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * 8
bpy.context.scene.camera = cam

bpy.ops.object.light_add(type='SUN', location=(3, 3, 8))
sun = bpy.context.active_object
sun.data.energy = 3
sun.rotation_euler = (math.radians(45), 0, math.radians(-45))

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = False
scene.world.color = (0.5, 0.5, 0.5)
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.resolution_x = 128 * SUPERSAMPLE
scene.render.resolution_y = 128 * SUPERSAMPLE
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {OUTPUT_PATH}")
