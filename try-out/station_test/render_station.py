"""
pak128 駅舎用 1x1x1 タイルのイソメトリックレンダリング
出力: 128x128px RGBA PNG（makeobjに渡す素材）
"""

import bpy
import math
import mathutils
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "station_cube.png")

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 1x1x1タイルの立方体（高さスケール 0.816 適用）
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.408))
cube = bpy.context.active_object
cube.scale = (1.0, 1.0, 0.816)

mat = bpy.data.materials.new(name="StationMat")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.75, 0.70, 0.60, 1.0)   # 駅舎らしいベージュ
    bsdf.inputs["Emission Color"].default_value = (0.75, 0.70, 0.60, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.25
cube.data.materials.append(mat)

# カメラ: 仰角30°, 方位角45° (Simutrans SE視点)
bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 1.8   # 128x128に合わせたスケール
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, 0.408))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * 8
bpy.context.scene.camera = cam

# 太陽光（NW方向から）
bpy.ops.object.light_add(type='SUN', location=(3, 3, 8))
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
print(f"RENDER_DONE: {OUTPUT_PATH}")
