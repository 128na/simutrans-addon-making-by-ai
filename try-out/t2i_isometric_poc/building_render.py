"""
Blender headless isometric render - t2i_isometric_poc 用の入力画像生成
CLAUDE.md記載のSimutrans標準カメラ設定（直交投影・俯角30°・方位45°）を踏襲しつつ、
try-out/blender/isometric_box.py の単純ボックスより少しだけ建物らしい
「箱＋切妻屋根」の簡易形状にして、ControlNetへの入力（canny/depth抽出元）として
情報量を増やす。

Usage:
    blender --background --python building_render.py

出力:
    output/building_render.png       RGBA カラー画像
    output/building_render_depth.png Z-depth（Mist pass経由、白= 近い/黒=遠い に正規化）
"""

import bpy
import math
import mathutils
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
COLOR_PATH = os.path.join(OUTPUT_DIR, "building_render.png")
DEPTH_PATH = os.path.join(OUTPUT_DIR, "building_render_depth.png")

# --- Clear default scene ---
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# --- Building body (box, same height convention as isometric_box.py) ---
BODY_H = 0.816  # height = side * sqrt(6)/3
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, BODY_H / 2))
body = bpy.context.active_object
body.name = "BuildingBody"
body.scale = (1.0, 1.0, BODY_H)

mat_body = bpy.data.materials.new(name="BodyMat")
mat_body.use_nodes = True
bsdf = mat_body.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.62, 0.45, 0.32, 1.0)  # 木造っぽい茶色
    bsdf.inputs["Emission Color"].default_value = (0.62, 0.45, 0.32, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.25
body.data.materials.append(mat_body)

# --- Roof (gable/triangular prism, sitting on top of the body) ---
ROOF_H = 0.5
roof_base_z = BODY_H
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, roof_base_z + ROOF_H / 2))
roof = bpy.context.active_object
roof.name = "Roof"
roof.scale = (0.58, 0.58, ROOF_H)
# gableへ変形: 上面の2辺を中央に寄せてridge lineを作る（切妻屋根）
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bm_verts = roof.data.vertices
bpy.ops.object.mode_set(mode='OBJECT')
for v in roof.data.vertices:
    if v.co.z > 0:  # 上面の頂点
        v.co.y = 0.0  # Y方向に潰してridgeにする（X方向に稜線が通る切妻屋根）
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.object.mode_set(mode='OBJECT')

mat_roof = bpy.data.materials.new(name="RoofMat")
mat_roof.use_nodes = True
bsdf_r = mat_roof.node_tree.nodes.get("Principled BSDF")
if bsdf_r:
    bsdf_r.inputs["Base Color"].default_value = (0.35, 0.18, 0.15, 1.0)  # 瓦っぽい暗い赤茶
    bsdf_r.inputs["Emission Color"].default_value = (0.35, 0.18, 0.15, 1.0)
    bsdf_r.inputs["Emission Strength"].default_value = 0.2
roof.data.materials.append(mat_roof)

# --- Orthographic camera (Simutrans標準: elevation 30° azimuth 45°) ---
bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
# 2026-07-08 フィードバック対応: 当初 ortho_scale=2.4 で「屋根込みの全体が収まるよう
# マージンを持たせる」実装にしていたが、これは try-out/blender/isometric_box.py・
# CLAUDE.md記載の「1×1 BUタイル -> 画面幅ぴったり」という標準キャリブレーション
# (ortho_scale=sqrt(2)) から外れており、結果としてBlenderレンダリングの建物接地面が
# Simutransのベースタイル菱形（try-out/t2i_inpaint_poc/crop.png基準）に対して
# 小さく・中央寄りにズレる問題があった（diag_tile_marker.pyで実測・検証済み）。
# 標準キャリブレーション(ortho_scale=sqrt(2))に戻しつつ、屋根の分だけ縦方向の
# キャンバスを拡張(resolution_y>resolution_x)し、sensor_fit='HORIZONTAL'で
# 横幅基準のスケールを維持したまま、shift_yで「タイル菱形をキャンバス最下部に
# 常に接地させる」ようフレーミングを補正した。
cam.data.ortho_scale = math.sqrt(2)
cam.data.sensor_fit = 'HORIZONTAL'
cam.data.shift_y = 0.25
cam.data.clip_start = 0.1
cam.data.clip_end = 20.0
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, BODY_H / 2))
distance = 8
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * distance

bpy.context.scene.camera = cam

# --- Sun light from upper-left (NW) ---
bpy.ops.object.light_add(type='SUN', location=(3, 3, 8))
sun = bpy.context.active_object
sun.data.energy = 3
sun.rotation_euler = (math.radians(45), 0, math.radians(-45))

# --- Render settings (color pass) ---
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = 256
scene.render.resolution_y = 384  # 屋根の分だけ上方向にヘッドルームを確保（タイル菱形は最下部に接地）
scene.render.filepath = COLOR_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE color: {COLOR_PATH}")

# NOTE: Blender 5.x のコンポジタAPI変更（scene.node_tree -> scene.compositing_node_group、
# CompositorNodeComposite/OutputFileノードの仕様変更）に手間取ったため、
# 本物のZ-depth/Mistパス出力は今回のPoCでは見送った（コスト対効果の判断）。
# depth map はこの後 preprocess_edges_depth.py 側でアルファチャンネルからの
# 簡易プロキシ（distance transform）として生成する。
