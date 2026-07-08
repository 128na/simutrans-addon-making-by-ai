"""
【診断用】building_render.py と同じカメラ設定で、原点中心の1x1 BUの地面タイル
(マゼンタ平面, z=0)だけを単体でレンダリングし、現状のカメラ設定で
「1タイル分の地面」が画像内のどこに投影されるかを可視化する。

fasitバリデーション用: try-out/t2i_inpaint_poc/crop.png のタイル菱形と比較して
現状のズレを定量化するための基準画像を作る。

Usage:
    blender --background --python diag_tile_marker.py
"""

import bpy
import math
import mathutils
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUTPUT_DIR, "diag_tile_marker.png")

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 1x1 BU の地面タイル平面（z=0、原点中心）
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.001))
plane = bpy.context.active_object
plane.name = "TileMarker"
mat = bpy.data.materials.new(name="MarkerMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (1.0, 0.0, 1.0, 1.0)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.0, 1.0, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 1.0
plane.data.materials.append(mat)

# --- building_render.py と全く同じカメラ設定 ---
bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2)
cam.data.sensor_fit = 'HORIZONTAL'  # resolution_y > resolution_x でも横幅基準のscaleを維持
cam.data.shift_y = 0.25
cam.data.clip_start = 0.1
cam.data.clip_end = 20.0
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
BODY_H = 0.816
target = mathutils.Vector((0, 0, BODY_H / 2))
distance = 8
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * distance

bpy.context.scene.camera = cam

bpy.ops.object.light_add(type='SUN', location=(3, 3, 8))
sun = bpy.context.active_object
sun.data.energy = 3

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = 256
scene.render.resolution_y = 384
scene.render.filepath = OUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE marker: {OUT_PATH}")
