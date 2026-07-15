"""
pak128 道路（完全平面）レンダリング
出力: 512x512px RGBA PNG（"_raw"、postprocess.pyで128x128に変換してway dat用にする）

立体物(box)ではなく厚み0のplaneで地面と完全に同じ高さの平面形状を試す。
中央にセンターラインを重ねて、平面が正しい向き・位置でレンダリングされているか
目視確認しやすくする（ラインは0.001BUだけ持ち上げてz-fightingを回避、厚みとしては無視できる量）。

4倍(SUPERSAMPLE)の解像度でレンダリングしてから縮小するのは、タイル境界(平面の外周)が
アンチエイリアスでそのまま半透明ピクセルになるとタイルを連続設置したときに隙間として
見えてしまうため（ユーザー実機確認で指摘）。縮小後にpostprocess.pyでアルファを
0/255の二値にハード閾値処理し、半透明ピクセルを残さないようにする。
"""

import bpy
import math
import mathutils
import os

SUPERSAMPLE = 4
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "road_flat_raw.png")

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 路面: 厚み0の平面（1x1 BU）
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
road = bpy.context.active_object
road.name = "RoadSurface"

road_mat = bpy.data.materials.new(name="RoadMat")
road_mat.use_nodes = True
bsdf = road_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.22, 0.22, 0.24, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.22, 0.22, 0.24, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.2
road.data.materials.append(road_mat)

# センターライン: ごくわずかに持ち上げた細長い平面（南北方向）
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.001))
line = bpy.context.active_object
line.name = "CenterLine"
line.scale = (0.02, 0.85, 1.0)  # ユーザー確認で「太め、半分でよい」との指摘を受けて0.04→0.02に

line_mat = bpy.data.materials.new(name="LineMat")
line_mat.use_nodes = True
bsdf = line_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.85, 0.75, 0.35, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.85, 0.75, 0.35, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.3
line.data.materials.append(line_mat)

# カメラ: 仰角30°, 方位角45° (Simutrans SE視点)
bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2)  # 1タイル(1×1 BU)がぴったり128pxに
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
# 注視点Zは常に0.408(=1フロア相当0.816の半分)に固定する。
# これはオブジェクト自身の高さとは無関係な「キャンバス内の地面位置」の固定アンカーで、
# station_cube(高さ0.816のbox)の注視点0.408がそのまま流用できる値だと後で判明した
# （地面ぴったりの平面をtarget=0でレンダリングしたところ、ゲーム内でタイル上空32pxに
#  浮いて表示された。target=0.408に直すことで解消）。
GROUND_ANCHOR_Z = 0.408
target = mathutils.Vector((0, 0, GROUND_ANCHOR_Z))
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
scene.render.resolution_x = 128 * SUPERSAMPLE
scene.render.resolution_y = 128 * SUPERSAMPLE
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {OUTPUT_PATH}")
