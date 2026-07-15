"""
pak128 線路（道床＋レールの厚み分だけ盛り上がる形状）レンダリング
出力: 512x512px RGBA PNG（"_raw"、postprocess.pyで128x128に変換してway dat用にする）

立体の建物(box, 高さ0.816 BU = 1フロア相当)ではなく、道床(バラスト)+レール2本ぶんだけ
わずかに盛り上がった薄い形状を試す。

寸法はBlender単位(BU)ではなく、実機のpak128参照画像(rail_100_tracks.png等)で目視した
px数を基準に指定する。カメラ(ortho_scale=√2, 仰角60°/方位45°)固有の投影係数で
px→BUに変換する。係数はcam_probe(下記コメント)で実測済み:
- 垂直(Z軸)方向: 1BU = (128/√2) × cos(30°) ≈ 78.38px
- 水平(X軸 or Y軸)方向: 1BU = (128/√2) × cos(45°) = 128/2 = 64.0px（ちょうど半分になる）

4倍(SUPERSAMPLE)の解像度でレンダリングしてから縮小するのは、タイル境界がアンチエイリアスで
半透明ピクセルになりタイルを連続設置したときに隙間として見えてしまうため
（ユーザー実機確認で指摘）。postprocess.pyで縮小後にアルファを0/255の二値にする。
"""

import bpy
import math
import mathutils
import os

SUPERSAMPLE = 4
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "rail_flat_raw.png")

PX_PER_BU_Z = (128 / math.sqrt(2)) * math.cos(math.radians(30))  # ≈78.38 px/BU（縦）
PX_PER_BU_HORIZ = 128 / 2  # = 64.0 px/BU（横、X軸・Y軸オフセットとも同じ）

BALLAST_HEIGHT_PX = 1.0   # 道床(バラスト)の高さ: pak128参照で約1px
RAIL_HEIGHT_PX = 1.0      # レールが道床からさらに盛り上がる高さ: pak128参照で約1px
RAIL_GAUGE_PX = 10.0      # レール2本の中心間隔（画面横方向）: pak128参照でEW方向約10px

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 手前(near)/奥(far)で異なる下げ量(手前1px, 奥3px、差は2px)が必要（pak128デフォルト
# 線路との接続に合わせる要求）。3案を試した:
#  1. 道床を手前/奥に分割してZで2px差をつける → 道床に段差ができて却下
#  2. 道床は分割せず、差の2px全部をレールのX(横)シフトで作る → ゲージが手前+2px/
#     奥+6pxずれ、「両方手前に寄りすぎ(横4px分)」と指摘
#  3(採用). 2pxの差をZとXに半分ずつ分割する: 道床にごく小さい1px分の段差をつけつつ、
#     残り1pxはレールのXシフトで作る。ゲージのズレを半分(手前+0px/奥+2px)に抑えつつ、
#     道床の段差も半分(1px)に抑える折衷案
BALLAST_WIDTH = 0.65
NEAR_BALLAST_DOWN_PX = 1.0   # 道床(手前側)の基準の下げ量
FAR_BALLAST_STEP_PX = 1.0    # 道床(奥側)は手前よりさらにこの分だけ低くする
FAR_RAIL_X_SHIFT_PX = 1.0    # 奥レールの残り1px分はXシフトで作る（Yは継ぎ目上使えない）
PX_PER_BU_HORIZ_TO_DY = 32.0  # 世界X 1BUあたりの画面縦方向(dy)寄与

ballast_h = BALLAST_HEIGHT_PX / PX_PER_BU_Z
ballast_mat = bpy.data.materials.new(name="BallastMat")
ballast_mat.use_nodes = True
bsdf = ballast_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.40, 0.36, 0.30, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.40, 0.36, 0.30, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.2

ballast_halves = [
    (BALLAST_WIDTH / 4, "Ballast_near", NEAR_BALLAST_DOWN_PX),
    (-BALLAST_WIDTH / 4, "Ballast_far", NEAR_BALLAST_DOWN_PX + FAR_BALLAST_STEP_PX),
]
for x_center, name, down_px in ballast_halves:
    z = ballast_h / 2 - (down_px / PX_PER_BU_Z)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x_center, 0, z))
    ballast = bpy.context.active_object
    ballast.name = name
    ballast.scale = (BALLAST_WIDTH / 2, 1.0, ballast_h)
    ballast.data.materials.append(ballast_mat)

# レール2本: それぞれの真下の道床から1px突き出るように、真下の道床の下げ量に
# 合わせてZを揃える。奥だけ残り1px分をXシフト（手前方向）で追加する
rail_h = RAIL_HEIGHT_PX / PX_PER_BU_Z
rail_mat = bpy.data.materials.new(name="RailMat")
rail_mat.use_nodes = True
bsdf = rail_mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.14, 0.14, 0.16, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.30, 0.30, 0.33, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.15

rail_gauge_bu = RAIL_GAUGE_PX / PX_PER_BU_HORIZ  # レール中心間隔をBUに変換

rails = [
    (-rail_gauge_bu / 2 + FAR_RAIL_X_SHIFT_PX / PX_PER_BU_HORIZ_TO_DY,
     "Rail_far", NEAR_BALLAST_DOWN_PX + FAR_BALLAST_STEP_PX),
    (rail_gauge_bu / 2, "Rail_near", NEAR_BALLAST_DOWN_PX),
]
for offset_x, rail_name, down_px in rails:
    z = ballast_h + rail_h / 2 - (down_px / PX_PER_BU_Z)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(offset_x, 0, z))
    rail = bpy.context.active_object
    rail.name = rail_name
    rail.scale = (0.02, 1.0, rail_h)
    rail.data.materials.append(rail_mat)

# カメラ: 仰角30°, 方位角45° (Simutrans SE視点)
bpy.ops.object.camera_add(location=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2)  # 1タイル(1×1 BU)がぴったり128pxに
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()
# 注視点Zは常に0.408(=1フロア相当0.816の半分)に固定する。オブジェクト自身の中心
# (rail_top_z/2)ではない。render_road.pyと同じ固定アンカーで、これを守らないと
# ゲーム内でタイル上空に浮いて表示される（詳細はrender_road.pyのコメント参照）
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
print(f"ballast_h={ballast_h:.4f}BU({BALLAST_HEIGHT_PX}px) rail_h={rail_h:.4f}BU({RAIL_HEIGHT_PX}px) "
      f"rail_gauge={rail_gauge_bu:.4f}BU({RAIL_GAUGE_PX}px)")
