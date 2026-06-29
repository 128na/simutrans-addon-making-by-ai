"""
Blender headless isometric render - proof of concept
Simutrans pak128 向けイソメトリック視点でボックスをレンダリングする

Usage:
    blender --background --python isometric_box.py

Camera spec (from Metasequoia tutorial https://ahozura.kasu.me/portal/?p=666):
- Projection: Orthographic
- Elevation (pitch): 30° → Blender X rotation = 60°
- Azimuth (head):   45° SE = Simutrans main view
- Height scale: X:Y:Z = 100:81.6:100 (height = side × √6/3 ≈ 0.816)
- Self-illumination 0.2~0.3 to compensate dark side faces

Blender 5.1 notes:
- render engine: 'BLENDER_EEVEE' (not BLENDER_EEVEE_NEXT)
- use_nodes deprecated in 6.0 but works in 5.x
"""

import bpy
import math
import mathutils
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "output", "isometric_box.png")
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Box with corrected height scale (100:81.6:100)
# height = 0.816, so z center = 0.408
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.408))
cube = bpy.context.active_object
cube.scale = (1.0, 1.0, 0.816)

mat = bpy.data.materials.new(name="BuildingMat")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.6, 0.4, 0.3, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.6, 0.4, 0.3, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.25
cube.data.materials.append(mat)

# Orthographic camera
# elevation 30° → X rotation = 60°, azimuth 45°
bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 2.5
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

# Compute camera position: place it so it looks at the object center
bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, 0.408))
distance = 8
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * distance

bpy.context.scene.camera = cam

# Sun light from upper-left (NW)
bpy.ops.object.light_add(type='SUN', location=(3, 3, 8))
sun = bpy.context.active_object
sun.data.energy = 3
sun.rotation_euler = (math.radians(45), 0, math.radians(-45))

# Render settings
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = 256
scene.render.resolution_y = 256
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {OUTPUT_PATH}")
