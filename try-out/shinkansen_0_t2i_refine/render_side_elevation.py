"""
0系新幹線 先頭車両 - 真の側面図(true side elevation)単体レンダリング (t2i差分反復用・追加実験)

render_0series_s.py の "s方向" は shinkansen_0/render_0series.py の固定等角(isometric)カメラ
（仰角60°=水平から30°見下ろし、方位45°）に対して車両をZ軸180°回転させただけの斜め見下ろし視点
であり、真の側面図(真横・仰角0°)ではなかった。ユーザーから「t2i画像のアングルが完全には
合っていない」という指摘を受け、「SDXLは新幹線の真横プロフィール写真を大量に学習しているはず
なので、仰角0°の真の側面図の方がcanny誘導でも構図が安定するのでは」という仮説を検証するために
本スクリプトを追加した。

create_train_shell関数はrender_0series_s.py(Round3、WINDOW_ZONES込み)のパラメータをそのまま流用し、
カメラだけを「車両の長さ方向(Y軸)に対して直角な水平方向から、仰角0°で見る」正射影に変更する。
車両を回転させず、カメラ自体を側面に配置する（mathutils.Vector.to_track_quat()でカメラのlocal -Z軸
を車両中心へ向け、local Y軸を極力ワールドZ(上方向)に合わせる、Blender標準の"look-at"手法を使用）。

Usage:
    blender --background --python render_side_elevation.py
"""
import bpy
import bmesh
import math
import mathutils
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# モデルパラメータ（render_0series_s.py Round3をベースに、シルエットIoU計測での
# 差分反復ラウンドごとに更新する。変更履歴はREADME.mdの「シルエットIoU計測」参照）
# ============================================================
# --- IoU round1: target_side_reference.pngとの側面シルエット比較で、ノーズ先端が
#     target(鋭く尖った剣先型)に対して現行(丸く鈍い団子鼻)すぎると判明 → TIP_FRACを
#     大きく下げて先端を鋭く、NOSE_Lを伸ばしてテーパーをより長く緩やかにした ---
# --- IoU round2: round1後もIoUがほぼ横ばい(66.5%→66.9%)だったため、bboxのアスペクト比
#     (幅/高さ)を実測して比較したところ render=4.91 target=6.83 で「現行モデルは横に対して
#     縦に厚すぎる(寸胴)」ことが判明。ortho_scaleは全長(BODY_L+NOSE_L)だけで決まり
#     CAR_Hには依存しないため、CAR_Hだけを下げれば横幅を変えず高さのみ縮められる計算
#     (0.33 × 75/115 × 368/785 ≈ 0.237) → CAR_Hを0.33→0.24に変更 ---
# --- IoU round3: round2でもIoUがほぼ横ばい(66.9%→66.2%、誤差レベル)だったため、
#     正規化後マスクの「幅方向の各位置での高さ(span)」を数値化して比較したところ、
#     target(半値幅に落ちるx位置≈0.885)に対しrender(≈0.951)がノーズ先端寄りに偏っており、
#     先端付近でのみ急に絞られている(丸みが先端に集中しすぎ)と判明。BODY_Lを縮め
#     NOSE_Lを伸ばしてノーズが全長に占める比率を上げ、半値幅位置を前方へ動かす方向で調整。
#     ただし計算上、tip_frac=0.08のままでは半値位置をtarget水準まで動かすには
#     nose_frac(NOSE_L/(BODY_L+NOSE_L))が1に漸近する必要があり(=ほぼ全身がノーズ)、
#     現実的な範囲では到達しきれない構造的な限界と判明（詳細はREADME参照）。
#     ここでは現実的な範囲での改善として、BODY_L↓/NOSE_L↑のみ実施した ---
BODY_L = 0.55   # 車体長（Y方向, 前方が+Y, 後端y=0基準） (0.80→0.55: ノーズ比率を上げる)
NOSE_L = 0.65   # ノーズ突出長 (0.60→0.65: ノーズ比率を上げる)
CAR_W  = 0.30   # 車幅（X方向）
CAR_H  = 0.24   # 車高（Zスケール前） (0.33→0.24: bboxアスペクト比を実測してtargetに近づけた)
STRIPE_H_FRAC = 0.40   # 青帯が占める高さの割合(下から)
TIP_FRAC = 0.08        # 先端の丸み(大きいほど団子鼻、小さいほど尖る) (0.20→0.08: targetの鋭い先端に寄せる)
SUPERELLIPSE_N = 6.0   # 断面の角丸具合(小さいほど楕円、大きいほど角ばった長方形)
RINGS_BODY = 3
RINGS_NOSE = 14
SEGMENTS = 28

# 客室窓(細い帯)・運転席窓(ノーズ側の大きい窓)の2ゾーン(render_0series_s.py Round3と同一)
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

# ---- 親エンプティ（本スクリプトでは回転させず常に基準姿勢のまま）----
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

# ---- カメラ（真の側面図: 仰角0°、車両の長さ方向(Y軸)に対し直角な水平方向から見る）----
# 車両はY軸方向(前方+Y)に伸びており、shell.location.y=-BODY_L/2起点で
# world Y範囲は[-BODY_L/2, BODY_L/2+NOSE_L]（ノーズがある分+Y側に長い）。
# 中心を狙うにはY方向の中点 NOSE_L/2 をターゲットにする。
bpy.ops.object.camera_add()
cam = bpy.context.active_object
cam.name = "SideCam"
cam.data.type = 'ORTHO'
# 全長(BODY_L+NOSE_L)が正方形フレームに収まるよう余白付きでスケールする
train_length = BODY_L + NOSE_L
cam.data.ortho_scale = train_length * 1.4

target_y = NOSE_L / 2
target = mathutils.Vector((0, target_y, Z_BODY))
# カメラをワールドX軸上の遠方に置き、-X方向を向いて車両の側面を正面から見る
cam_pos = target + mathutils.Vector((10.0, 0, 0))
cam.location = cam_pos
direction = target - cam_pos
# local -Z軸(カメラの向く方向)をdirectionへ、local Y軸(画面上方向)をワールドZに極力揃える
# 標準的なBlenderの「カメラをターゲットに向ける」手法(to_track_quat)。
# これによりcam.location.z == target.z なので仰角(pitch)は正確に0°になる。
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

bpy.context.view_layer.update()

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

out_path = os.path.join(OUTPUT_DIR, "0series_side_elevation.png")
scene.render.filepath = out_path
bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: side_elevation -> {out_path}")
