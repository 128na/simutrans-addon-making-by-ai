"""
pak128 建物用アイコン/カーソル画像レンダリング
出力: 48x48px RGBA PNG（cursor / icon フィールド用）
"""

import bpy
import math
import mathutils
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "station_icon.png")

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.408))
cube = bpy.context.active_object
cube.scale = (1.0, 1.0, 0.816)

mat = bpy.data.materials.new(name="IconMat")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.75, 0.70, 0.60, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.75, 0.70, 0.60, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.3
cube.data.materials.append(mat)

bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 1.9
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, 0.408))
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
scene.world.color = (0.5, 0.5, 0.5)  # グレー背景
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.resolution_x = 128
scene.render.resolution_y = 128
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {OUTPUT_PATH}")
