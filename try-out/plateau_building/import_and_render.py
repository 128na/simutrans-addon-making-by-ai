"""
PLATEAU (東京都23区 LOD2, meshcode 53394515) の建物1棟を
Simutrans pak128 のイソメトリック画像に変換する検証スクリプト。

入力: source_53394515/53394515_bldg_6677.obj (実寸メートル, Z-up)
出力: building.png (128x128 RGBA)
"""

import bpy
import math
import mathutils
import os

BASE = os.path.dirname(__file__)
OBJ_PATH = os.path.join(BASE, "source_53394515", "53394515_bldg_6677.obj")
OUTPUT_PATH = os.path.join(BASE, "building.png")

TILE_FIT_MARGIN = 1.05  # タイル目一杯に収める際の余白倍率(5%前後)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

bpy.ops.wm.obj_import(filepath=OBJ_PATH, forward_axis='Y', up_axis='Z')

imported = [o for o in bpy.context.selected_objects if o.type == 'MESH']
print(f"IMPORTED_OBJECTS: {len(imported)}")
if len(imported) > 1:
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.join()
    imported = [bpy.context.active_object]

building = imported[0]
bpy.context.view_layer.update()

# バウンディングボックス（ワールド座標）を計算し、XY中心・Z下端を原点に合わせる
corners = [building.matrix_world @ mathutils.Vector(c) for c in building.bound_box]
xs = [c.x for c in corners]
ys = [c.y for c in corners]
zs = [c.z for c in corners]
center_x = (min(xs) + max(xs)) / 2
center_y = (min(ys) + max(ys)) / 2
min_z = min(zs)
span_x = max(xs) - min(xs)
span_y = max(ys) - min(ys)
span_z = max(zs) - min(zs)
print(f"FOOTPRINT_M: x={span_x:.1f} y={span_y:.1f} height={span_z:.1f}")

building.location.x -= center_x
building.location.y -= center_y
building.location.z -= min_z
bpy.context.view_layer.update()

# フットプリント/高さの最大辺を基準にortho_scaleを自動決定し、建物がタイル目一杯
# (TILE_FIT_MARGIN分の余白)に収まるようにする。station_test/render_station.pyで
# 検証済みの「tile_side(BU) × √2」と同じ式を、固定のタイル実寸(m)想定ではなく
# 建物自身の実測フットプリントに一般化したもの
fit_span = max(span_x, span_y, span_z)

cam_data = bpy.data.cameras.new("IsoCam")
cam = bpy.data.objects.new("IsoCam", cam_data)
bpy.context.collection.objects.link(cam)
cam.data.type = 'ORTHO'
cam.data.ortho_scale = fit_span * math.sqrt(2) * TILE_FIT_MARGIN
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

# 接地アンカー: pak128の128x128タイル画像規約では下半分が地面で、ベースタイルの
# 菱形((64,0),(128,32),(64,64),(0,32)、画像下端起点)の中心は画像下端から32px
# = 上端起点(row)では128-32=96になる。つまり接地点はキャンバス中心(row64)ではなく
# そこからさらに32px下が正しいアンカー位置。建物自身の高さ(span_z)には依存させず、
# ortho_scaleのみから必要なworld Zオフセットを算出する
# (shinkansen_0/render_0series.pyで実証済みの変換式 PX_PER_UNIT = 128/ortho_scale×cos30° を流用)
px_per_unit = 128 / cam.data.ortho_scale * math.cos(math.radians(30))
target_z = 32 / px_per_unit

bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, target_z))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
distance = fit_span * 4
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
scene.render.resolution_x = 128
scene.render.resolution_y = 128
scene.render.filepath = OUTPUT_PATH

bpy.ops.render.render(write_still=True)

# makeobjはPNGの不透明ピクセルからbboxを自動検出してクロップし、そのオフセットが
# そのままゲーム内の描画位置になる(refs/simutrans image_writer.cc の init_dim/write_obj)。
# 建物がタイルに対して小さいほどクロップ由来の位置ズレが目立つため、4隅に不透明1px
# マーカーを焼き込み強制的に128x128フルキャンバスでパックさせる
# (knowledge.md「vehicleの接地位置ズレ対策」と同じ対策をbuildingにも適用)
img = bpy.data.images.load(OUTPUT_PATH)
w, h = img.size
pixels = list(img.pixels)
for cx, cy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
    i = (cy * w + cx) * 4
    pixels[i:i + 4] = [0.0, 0.0, 0.0, 1.0]
img.pixels[:] = pixels
img.filepath_raw = OUTPUT_PATH
img.file_format = 'PNG'
img.save()
bpy.data.images.remove(img)

print(f"RENDER_DONE: {OUTPUT_PATH}")
