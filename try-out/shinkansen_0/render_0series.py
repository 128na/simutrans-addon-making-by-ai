"""
0系新幹線 先頭車両 - 8方向イソメトリックレンダリング (Phase 1)
モデル: 車体+ノーズを1枚の継ぎ目なしメッシュとして生成（角丸長方形断面が
先端に向けて団子鼻状に丸く収束）。青帯も別オブジェクトにせず、同じメッシュの
下部フェイスにマテリアルを割り当てることでテーパーに自動追従させる。
出力: 128x128px RGBA PNG × 8ファイル
"""
import bpy
import bmesh
import math
import mathutils
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

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

mat_white = make_emission_mat("CarWhite", 0.93, 0.93, 0.93)
mat_blue  = make_emission_mat("CarBlue",  0.05, 0.20, 0.72)
mat_gray  = make_emission_mat("CarGray",  0.30, 0.30, 0.30)  # 台車

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
                        segments=28, superellipse_n=4.5):
    """
    車体+ノーズを1つの継ぎ目なしメッシュとして生成。
    ローカルY軸が車両前方(長さ方向)。後端 y=0、ノーズ先端 y=body_l+nose_l。
    車体部分は一定の角丸長方形断面、ノーズ部分は同じ断面形状のまま
    団子鼻状(長めに太さを保ってから丸く収束)に縮小する。
    下部(z方向の下stripe_h_frac割合)は別マテリアル(青帯)を割り当てる。
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

    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for j in range(segments):
            j2 = (j + 1) % segments
            verts = [r0[j], r0[j2], r1[j2], r1[j]]
            f = bm.faces.new(verts)
            avg_z = sum(v.co.z for v in verts) / 4
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
    obj.data.materials.append(mat_white)  # index 0
    obj.data.materials.append(mat_blue)   # index 1
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj

# ---- モデル寸法 ----
# 高さスケール: Simutrans X:Y:Z = 100:100:81.6
HS = 0.816

BODY_L = 0.80   # 車体長（Y方向, 前方が+Y, 後端y=0基準）
NOSE_L = 0.40   # ノーズ突出長
CAR_W  = 0.34   # 車幅（X方向）
CAR_H  = 0.30   # 車高（Zスケール前）
STRIPE_H_FRAC = 0.40  # 青帯が占める高さの割合(下から)
TIP_FRAC = 0.34       # 先端の丸み(大きいほど団子鼻、小さいほど尖る)

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
scene.render.resolution_x = 128
scene.render.resolution_y = 128

# ---- 8方向レンダリング ----
# ノーズが +Y 方向を向く設計で、カメラが SE(Z=45°) 位置にある
# 各方向の車両 Z 回転: 0° = ノーズが画面奥左(N相当)
DIRECTIONS = [
    ("n",    0),
    ("ne",  45),
    ("e",   90),
    ("se",  135),
    ("s",   180),
    ("sw",  225),
    ("w",   270),
    ("nw",  315),
]

for dir_name, z_deg in DIRECTIONS:
    parent.rotation_euler = (0, 0, math.radians(z_deg))
    bpy.context.view_layer.update()

    out_path = os.path.join(OUTPUT_DIR, f"0series_{dir_name}.png")
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"RENDER_DONE: {dir_name} -> {out_path}")

print("ALL DIRECTIONS DONE")
