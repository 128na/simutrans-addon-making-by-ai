"""
複数タイル(X×Y)にまたがるPLATEAU建物を、tilecutterに渡すための
「1枚の大きな合成イソメトリック画像」としてレンダリングする。

単体タイル建物(plateau_building)とは異なり、タイル間の位置合わせが必要なため
「建物ごとにキャンバス一杯へ自動フィット」ではなく、固定の実寸/タイル換算値
(TILE_SIDE_M)を用いる。tilecutterの tile_to_screen() 関数(tc.py)が前提とする
座標系に合わせて、画像内の「タイルグリッド全体の中心」が建物の接地中心
(world X=Y=0, Z=0)と一致するようにカメラを配置する。
"""

import bpy
import math
import mathutils
import os
import sys

BASE = os.path.dirname(__file__)

TILE_SIDE_M = 18.0   # 1タイルあたりの実寸(m)。既存pak128.japanアドオン作者のマンションDims実例
                     # (1x1〜4x3)と不動産統計(中規模マンション建築面積からの逆算, 約15m四方)を
                     # 突き合わせた15〜20mの推定レンジの中間値として採用
PAKSIZE = 128
SUPERSAMPLE = 2      # この倍率でレンダリングし、後段(downscale_supersample.py)で
                     # 最終サイズへ高品質縮小することでジャギー/モアレを抑える

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
DIMS_X = int(argv[0]) if len(argv) > 0 else 2
DIMS_Y = int(argv[1]) if len(argv) > 1 else 2
OBJ_REL_PATH = argv[2] if len(argv) > 2 else os.path.join("source_53393597", "53393597_bldg_6677.obj")
OUTPUT_NAME = argv[3] if len(argv) > 3 else "multitile_raw.png"
Z_ROTATION_DEG = float(argv[4]) if len(argv) > 4 else 0.0

OBJ_PATH = os.path.join(BASE, OBJ_REL_PATH)
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

# 原点をバウンディングボックス中心に移す(回転の基準点を固定するため)。
# 非対称な形状の建物は、回転「後」に再計算した中心で再センタリングすると
# 方向ごとに基準点がずれ、マルチタイル4方向の内容が食い違う原因になる
# (回転前に一度だけ基準点を確定し、その点を軸に回転させる必要がある)
bpy.context.view_layer.objects.active = building
building.select_set(True)
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
bpy.context.view_layer.update()

# min_zはZ回転で変化しないため回転前に確定してよい
corners0 = [building.matrix_world @ mathutils.Vector(c) for c in building.bound_box]
min_z = min(c.z for c in corners0)

if Z_ROTATION_DEG:
    building.rotation_euler[2] += math.radians(Z_ROTATION_DEG)
    bpy.context.view_layer.update()

corners = [building.matrix_world @ mathutils.Vector(c) for c in building.bound_box]
xs = [c.x for c in corners]
ys = [c.y for c in corners]
zs = [c.z for c in corners]
span_x = max(xs) - min(xs)
span_y = max(ys) - min(ys)
span_z = max(zs) - min(zs)
print(f"FOOTPRINT_M: x={span_x:.1f} y={span_y:.1f} height={span_z:.1f}")
print(f"DIMS: {DIMS_X}x{DIMS_Y} (tile_side={TILE_SIDE_M}m -> grid covers "
      f"{DIMS_X*TILE_SIDE_M:.0f}m x {DIMS_Y*TILE_SIDE_M:.0f}m)")

# object.originが既にバウンディングボックス中心(回転の基準点)なので、
# location.x/yをそのまま0にすればよい(回転後も基準点はズレない)
building.location.x = 0
building.location.y = 0
building.location.z -= min_z
bpy.context.view_layer.update()

# 1タイル(TILE_SIDE_M四方)がpak画像上でぴったり128pxになる基準密度(px/m)。
# タイル数(DIMS_X,Y)に依らず常にこの密度を保つ必要がある
px_per_unit = PAKSIZE / (TILE_SIDE_M * math.sqrt(2)) * math.cos(math.radians(30))

# tilecutterのtile_to_screen()が前提とするグリッド全体の座標系:
# - 幅は常にキャンバス中央(width/2)がグリッド中心になる(X,Yに依らず対称)
# - 高さはtc.pyのtile_to_screen式から、Z段数1の場合の
#   グリッド中心行(screen_height基準)を逆算する
width = int((DIMS_X + DIMS_Y) * (PAKSIZE / 2))
diamond_height = int((DIMS_X + DIMS_Y) * (PAKSIZE / 4) + PAKSIZE / 2)
# 建物の高さぶんの余白(px換算 + 安全マージン)を上に足す
height_margin_px = int(span_z * px_per_unit * 1.2) + 40
height = diamond_height + height_margin_px

# Blenderのortho_scaleは(sensor_fit=AUTOのデフォルトで)解像度の大きい方の辺に対して
# 適用される。高さ(height)を建物の高さ分だけ幅より大きくすることがあるため、
# sensor_fit='HORIZONTAL'で常に幅(width)基準に固定し、高さを変えても密度が
# 変わらないようにする(AUTOのままだと高さ次第で基準軸が入れ替わりズームがずれる)
ortho_scale = TILE_SIDE_M * math.sqrt(2) * (width / PAKSIZE)

# tc.pyのtile_to_screen()は4隅タイルの「左上」抽出座標を返すため、
# タイル中心はそこからさらに半タイル(PAKSIZE/2)分下にずれる。
# avg_preflip = (X+Y+2)*(PAKSIZE/8) + PAKSIZE/2 は4隅タイルのyy(flip前, 左上基準)の平均
avg_preflip = (DIMS_X + DIMS_Y + 2) * (PAKSIZE / 8) + PAKSIZE / 2
grid_center_row = (height - avg_preflip) + PAKSIZE / 2  # post-flip, タイル中心
# 画像中央(height/2)を基準に、接地点(world Z=0)をgrid_center_rowへずらすための
# target_z(カメラターゲットのワールドZ)を算出
offset_from_center_px = grid_center_row - (height / 2)
target_z = offset_from_center_px / px_per_unit

print(f"CANVAS: {width}x{height}, target_z={target_z:.2f}")
print(f"SUPERSAMPLE: {SUPERSAMPLE}x -> rendering at {width*SUPERSAMPLE}x{height*SUPERSAMPLE}")

cam_data = bpy.data.cameras.new("IsoCam")
cam = bpy.data.objects.new("IsoCam", cam_data)
bpy.context.collection.objects.link(cam)
cam.data.type = 'ORTHO'
cam.data.ortho_scale = ortho_scale
cam.data.sensor_fit = 'HORIZONTAL'
cam.rotation_euler = (math.radians(60), 0, math.radians(45))
bpy.context.view_layer.update()

target = mathutils.Vector((0, 0, target_z))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
distance = TILE_SIDE_M * max(DIMS_X, DIMS_Y) * 4
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
scene.render.resolution_x = width * SUPERSAMPLE
scene.render.resolution_y = height * SUPERSAMPLE
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {OUTPUT_PATH} (supersampled {width*SUPERSAMPLE}x{height*SUPERSAMPLE}, "
      f"target size {width}x{height})")
