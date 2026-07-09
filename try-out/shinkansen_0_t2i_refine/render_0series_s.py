"""
0系新幹線 先頭車両 - s方向(真横)単体レンダリング (t2i差分反復用)

try-out/shinkansen_0/render_0series.py をベースに、s方向(z_deg=180)1枚だけを
レンダリングする簡易版。t2i目標画像とのレンダー差分を見ながら毎ラウンド
パラメータ(TIP_FRAC/NOSE_L/BODY_L/CAR_W/CAR_H/superellipse_n等)を編集して
再実行することを想定し、スクリプト冒頭にまとめて置いている。

Usage:
    blender --background --python render_0series_s.py
"""
import bpy
import bmesh
import math
import mathutils
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# モデルパラメータ（毎ラウンド編集する箇所）
# ============================================================
# --- Round2: target_reference.png(t2i, seed123)との差分を踏まえて調整 ---
# 差分1: ノーズが寸胴・丸すぎる(団子度が過剰) → NOSE_L↑ TIP_FRAC↓ で細長い弾丸型寄りに
# 差分2: 断面が扁平(潜水艦的) → CAR_W↓ CAR_H↑ SUPERELLIPSE_N↑ で縦長・角張った断面に
# 差分3: 窓が皆無 → window材質帯を追加(下記WINDOW_*)
BODY_L = 0.80   # 車体長（Y方向, 前方が+Y, 後端y=0基準）
NOSE_L = 0.50   # ノーズ突出長 (0.40→0.50: より長く絞り込む)
CAR_W  = 0.30   # 車幅（X方向） (0.34→0.30: 幅を絞る)
CAR_H  = 0.33   # 車高（Zスケール前） (0.30→0.33: 高さを出す)
STRIPE_H_FRAC = 0.40   # 青帯が占める高さの割合(下から)
TIP_FRAC = 0.20        # 先端の丸み(大きいほど団子鼻、小さいほど尖る) (0.34→0.20)
SUPERELLIPSE_N = 6.0   # 断面の角丸具合(小さいほど楕円、大きいほど角ばった長方形) (4.5→6.0)
RINGS_BODY = 3
RINGS_NOSE = 14
SEGMENTS = 28

# --- Round3: 客室窓(細い帯)と運転席窓(ノーズ側の大きいドーム状ガラス)を
#     分けて表現し、target_reference.pngの「丸窓+ノーズ側の大きい窓」感に寄せる ---
# 各要素は (y_frac_lo, y_frac_hi, z_frac_lo, z_frac_hi)
# y_frac: 全長(車体+ノーズ)に対する前後位置の割合(0が後端, 1がノーズ先端)
# z_frac: 断面高さに対する上下位置の割合(-1〜1, 0が中心)
WINDOW_ZONES = [
    (0.08, 0.62, 0.15, 0.62),   # 客室窓(細い帯、車体部分)
    (0.62, 0.94, 0.05, 0.72),   # 運転席窓(ノーズ側、より大きく高い位置まで)
]

# t2i用に高解像度レンダーが欲しい場合はここを上げる（ゲーム用は128固定だが
# canny edge抽出の品質を上げるため既定で512にしている）
RENDER_RES = 512

# ============================================================

# シーンクリア
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ---- マテリアル ----
def make_emission_mat(name, r, g, b):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Emission Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.20
    return mat

mat_white  = make_emission_mat("CarWhite", 0.93, 0.93, 0.93)
mat_blue   = make_emission_mat("CarBlue",  0.05, 0.20, 0.72)
mat_gray   = make_emission_mat("CarGray",  0.30, 0.30, 0.30)  # 台車
mat_window = make_emission_mat("CarWindow", 0.06, 0.07, 0.09)  # 窓(運転席+客室、暗色バンド)

def superellipse_xz(radius_factor, w, h, n, segments):
    """角丸長方形(スーパー楕円)の輪郭点。n=2で楕円、n大で角ばった長方形に近づく"""
    pts = []
    for j in range(segments):
        ang = 2 * math.pi * j / segments
        c, s = math.cos(ang), math.sin(ang)
        x = math.copysign(abs(c) ** (2.0 / n), c) * (w / 2) * radius_factor
        z = math.copysign(abs(s) ** (2.0 / n), s) * (h / 2) * radius_factor
        pts.append((x, z))
    return pts

def create_train_shell(name, body_w, body_h, body_l, nose_l, tip_frac,
                        stripe_h_frac, rings_body=3, rings_nose=14,
                        segments=28, superellipse_n=4.5,
                        window_zones=None):
    """
    車体+ノーズを1つの継ぎ目なしメッシュとして生成。
    ローカルY軸が車両前方(長さ方向)。後端 y=0、ノーズ先端 y=body_l+nose_l。
    車体部分は一定の角丸長方形断面、ノーズ部分は同じ断面形状のまま
    団子鼻状(長めに太さを保ってから丸く収束)に縮小する。
    下部(z方向の下stripe_h_frac割合)は別マテリアル(青帯)を割り当てる。
    window_zones=[(y_lo,y_hi,z_lo,z_hi), ...] を指定すると、断面高さ・全長に
    対する割合がいずれかのゾーンに該当する面を窓(暗色)マテリアルにする
    (客室窓の細帯・運転席窓の大きいガラス、を別ゾーンとして分けて表現できる)。
    """
    bm = bmesh.new()
    ys = [0.0]
    for i in range(1, rings_body + 1):
        ys.append(body_l * i / rings_body)
    for i in range(1, rings_nose + 1):
        ys.append(body_l + nose_l * i / rings_nose)

    rings = []
    for y in ys:
        if y <= body_l + 1e-9:
            rf = 1.0
        else:
            t = (y - body_l) / nose_l
            # 団子鼻プロファイル: sqrt(1-t^2)で先端付近まで太さを保ち
            # 最後だけ丸く収束させる(線形コサインより寸胴で丸い)
            rf = tip_frac + (1 - tip_frac) * math.sqrt(max(0.0, 1.0 - t * t))
        pts = superellipse_xz(rf, body_w, body_h, superellipse_n, segments)
        ring = [bm.verts.new((x, y, z)) for x, z in pts]
        rings.append(ring)

    stripe_z_thresh = -body_h / 2 + body_h * stripe_h_frac
    y_total = body_l + nose_l

    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        y_mid = (ys[i] + ys[i + 1]) / 2
        y_frac = y_mid / y_total
        for j in range(segments):
            j2 = (j + 1) % segments
            verts = [r0[j], r0[j2], r1[j2], r1[j]]
            f = bm.faces.new(verts)
            avg_z = sum(v.co.z for v in verts) / 4
            z_frac = avg_z / (body_h / 2)
            is_window = window_zones is not None and any(
                y_lo <= y_frac <= y_hi and z_lo <= z_frac <= z_hi
                for (y_lo, y_hi, z_lo, z_hi) in window_zones
            )
            if is_window:
                f.material_index = 2
            else:
                f.material_index = 1 if avg_z < stripe_z_thresh else 0

    f_back = bm.faces.new(reversed(rings[0]))
    f_back.material_index = 0
    f_tip = bm.faces.new(rings[-1])
    f_tip.material_index = 0

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat_white)   # index 0
    obj.data.materials.append(mat_blue)    # index 1
    obj.data.materials.append(mat_window)  # index 2
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj

# ---- モデル寸法 ----
# 高さスケール: Simutrans X:Y:Z = 100:100:81.6
HS = 0.816

Z_FLOOR = 0.02
Z_BODY  = Z_FLOOR + CAR_H * HS / 2

# ---- 親エンプティ（回転制御） ----
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
parent = bpy.context.active_object
parent.name = "Vehicle"

def add_mesh(obj):
    """親エンプティの子にする"""
    obj.parent = parent

# 車体+ノーズ（継ぎ目なし一体メッシュ、青帯もマテリアルとして内包）
shell = create_train_shell(
    "Shell",
    body_w=CAR_W,
    body_h=CAR_H * HS,
    body_l=BODY_L,
    nose_l=NOSE_L,
    tip_frac=TIP_FRAC,
    stripe_h_frac=STRIPE_H_FRAC,
    rings_body=RINGS_BODY,
    rings_nose=RINGS_NOSE,
    segments=SEGMENTS,
    superellipse_n=SUPERELLIPSE_N,
    window_zones=WINDOW_ZONES,
)
# 後端(y=0)が車体中心(-BODY_L/2)に来るよう配置
shell.location = (0, -BODY_L / 2, Z_BODY)
add_mesh(shell)

# 台車（車輪部、装飾用）
for ty in [-BODY_L * 0.3, BODY_L * 0.3]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, ty, Z_FLOOR))
    bogie = bpy.context.active_object
    bogie.name = f"Bogie_{ty:.2f}"
    bogie.scale = (CAR_W * 1.02, 0.12, 0.025 * HS)
    bogie.data.materials.append(mat_gray)
    add_mesh(bogie)

# ---- カメラ（SE視点固定）----
bpy.ops.object.camera_add()
cam = bpy.context.active_object
cam.name = "IsoCam"
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2) * 1.3  # 1タイル分 + 余白
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.view_layer.update()

# 実機テストで「20px下にずらすと線路に接する」と判明したため、
# カメラターゲットのZを上げて画面内の車両位置を20px分下げる
# 1 world unit(画面up方向投影) ≈ 128/ortho_scale px, さらにcamera_upのZ成分0.866を掛ける
PX_PER_UNIT = 128 / cam.data.ortho_scale * 0.866
TARGET_Z_OFFSET = 20 / PX_PER_UNIT  # ≈ 0.332

target = mathutils.Vector((0, 0, Z_BODY + TARGET_Z_OFFSET))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * 10
bpy.context.scene.camera = cam

# ---- ライト ----
bpy.ops.object.light_add(type='SUN', location=(3, 3, 8))
sun = bpy.context.active_object
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), 0, math.radians(-45))

# ---- レンダー設定 ----
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = RENDER_RES
scene.render.resolution_y = RENDER_RES

# ---- s方向(真横)のみレンダリング ----
# render_0series.py の DIRECTIONS 定義に合わせ、s方向は z_deg=180
parent.rotation_euler = (0, 0, math.radians(180))
bpy.context.view_layer.update()

out_path = os.path.join(OUTPUT_DIR, "0series_s.png")
scene.render.filepath = out_path
bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: s -> {out_path}")
