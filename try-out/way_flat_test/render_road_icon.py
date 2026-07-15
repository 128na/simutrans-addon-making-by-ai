"""
pak128 道路用アイコン/カーソル画像レンダリング
出力: 512x512px RGB PNG（"_raw"、postprocess.pyで128x128に変換してcursor/icon用にする）
"""

import bpy
import math
import mathutils
import os

SUPERSAMPLE = 4
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "road_icon_raw.png")

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
road = bpy.context.active_object

road_mat = bpy.data.materials.new(name="RoadIconMat")
road_mat.use_nodes = True
bsdf = road_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.22, 0.22, 0.24, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.22, 0.22, 0.24, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.2
road.data.materials.append(road_mat)

bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.001))
line = bpy.context.active_object
line.scale = (0.02, 0.85, 1.0)  # render_road.pyと同じ（詳細はそちらのコメント参照）

line_mat = bpy.data.materials.new(name="LineIconMat")
line_mat.use_nodes = True
bsdf = line_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.85, 0.75, 0.35, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.85, 0.75, 0.35, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.3
line.data.materials.append(line_mat)

bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 1.9  # アイコンは余白を持たせて全体が収まるように
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
GROUND_ANCHOR_Z = 0.408  # render_road.pyと同じ固定アンカー（詳細はそちらのコメント参照）
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
scene.world.color = (0.5, 0.5, 0.5)  # グレー背景（左上(0,0)不透過にするため）
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.resolution_x = 128 * SUPERSAMPLE
scene.render.resolution_y = 128 * SUPERSAMPLE
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {OUTPUT_PATH}")
