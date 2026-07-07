"""
PLATEAU (CityGML->OBJ変換済み配布データ) の建物1棟を Simutrans pak128 アドオンに
自動変換するパイプライン検証スクリプト (step2)。

流れ:
  1. G空間情報センター配布のzip(S3)から、ダウンロードせず該当建物のOBJ一式のみ
     range requestで抽出 (remotezip)
  2. OBJ頂点からフットプリント(m)を計算し、タイル内に収まるスケールを決定
  3. Blenderレンダリング用スクリプトをテンプレートから生成し、headlessで実行
  4. アイコン画像を合成(不透過化)
  5. .dat を生成 → dat_linter lint → makeobj pak128 でビルド

使い方:
  python convert.py <zip_url> <obj_entry_dir_in_zip> <output_name>

例:
  python convert.py \
    https://gic-plateau.s3.ap-northeast-1.amazonaws.com/2020/13100_tokyo23-ku_2020_obj_3_op.zip \
    13100_tokyo23-ku_2020_obj_3_op/bldg/lod2/53394515_bldg_6677_obj/ \
    auto_53394515
"""

import argparse
import os
import subprocess
import sys

from remotezip import RemoteZip
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
TILE_FIT_MARGIN = 1.05  # タイル目一杯に収める際の余白倍率(5%前後)


def fetch_building(zip_url, entry_dir, workdir):
    os.makedirs(workdir, exist_ok=True)
    obj_path = None
    with RemoteZip(zip_url) as z:
        for info in z.infolist():
            if info.filename.startswith(entry_dir) and not info.filename.endswith("/"):
                rel = info.filename[len(entry_dir):]
                outpath = os.path.join(workdir, rel)
                os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
                with z.open(info.filename) as src, open(outpath, "wb") as dst:
                    dst.write(src.read())
                if rel.endswith(".obj"):
                    obj_path = outpath
    if obj_path is None:
        raise RuntimeError(f"OBJ not found under {entry_dir}")
    return obj_path


def compute_footprint(obj_path):
    xs, ys, zs = [], [], []
    with open(obj_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                xs.append(float(x))
                ys.append(float(y))
                zs.append(float(z))
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def render_building(obj_path, output_png):
    script = f"""
import bpy, math, mathutils
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.wm.obj_import(filepath=r"{obj_path}", forward_axis='Y', up_axis='Z')
imported = [o for o in bpy.context.selected_objects if o.type == 'MESH']
if len(imported) > 1:
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.join()
    imported = [bpy.context.active_object]
building = imported[0]
bpy.context.view_layer.update()
corners = [building.matrix_world @ mathutils.Vector(c) for c in building.bound_box]
xs=[c.x for c in corners]; ys=[c.y for c in corners]; zs=[c.z for c in corners]
cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2; minz=min(zs)
span_x = max(xs)-min(xs); span_y = max(ys)-min(ys); span_z = max(zs)-min(zs)
building.location.x -= cx
building.location.y -= cy
building.location.z -= minz
bpy.context.view_layer.update()
# フットプリント/高さの最大辺を基準にortho_scaleを自動決定し、建物がタイル目一杯
# ({TILE_FIT_MARGIN}倍の余白)に収まるようにする(import_and_render.pyと同じ式)
fit_span = max(span_x, span_y, span_z)
cam_data = bpy.data.cameras.new("IsoCam")
cam = bpy.data.objects.new("IsoCam", cam_data)
bpy.context.collection.objects.link(cam)
cam.data.type = 'ORTHO'
cam.data.ortho_scale = fit_span * math.sqrt(2) * {TILE_FIT_MARGIN}
cam.rotation_euler = (math.radians(60), 0, math.radians(45))
# 接地アンカー: pak128の128x128タイル画像規約では下半分が地面で、ベースタイルの
# 菱形((64,0),(128,32),(64,64),(0,32)、画像下端起点)の中心は画像下端から32px
# = 上端起点(row)では128-32=96になる。建物自身の高さ(span_z)には依存させず、
# ortho_scaleのみから必要なworld Zオフセットを算出する(import_and_render.pyと同じ式)
px_per_unit = 128 / cam.data.ortho_scale * math.cos(math.radians(30))
target_z = 32 / px_per_unit
bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, target_z))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * (fit_span * 4)
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
scene.render.filepath = r"{output_png}"
bpy.ops.render.render(write_still=True)
# makeobjの自動クロップによる位置ズレ対策として4隅に不透明1pxマーカーを焼き込み、
# 強制的に128x128フルキャンバスでパックさせる(import_and_render.pyと同じ対策)
img = bpy.data.images.load(r"{output_png}")
w, h = img.size
pixels = list(img.pixels)
for cx2, cy2 in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
    i = (cy2 * w + cx2) * 4
    pixels[i:i + 4] = [0.0, 0.0, 0.0, 1.0]
img.pixels[:] = pixels
img.filepath_raw = r"{output_png}"
img.file_format = 'PNG'
img.save()
bpy.data.images.remove(img)
print("RENDER_DONE")
"""
    script_path = output_png + ".render.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    result = subprocess.run(
        ["blender", "--background", "--python", script_path],
        capture_output=True, text=True,
    )
    if "RENDER_DONE" not in result.stdout:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Blender render failed")


def make_icon(building_png, icon_png):
    img = Image.open(building_png).convert("RGBA")
    bg = Image.new("RGBA", img.size, (180, 180, 180, 255))
    bg.alpha_composite(img)
    bg.convert("RGB").save(icon_png)


DAT_TEMPLATE = """obj=building
name={name}
copyright=PLATEAU (MLIT) building, auto-converted for pipeline test
type=extension
waytype=track
enables_pax=1
level=4
NoInfo=1
Dims=1,1,4
intro_year=1900
retire_year=2999

cursor={name}_icon.png.0.0
icon={name}_icon.png.0.0

BackImage[0][0][0][0][0]={name}.png.0.0
BackImage[1][0][0][0][0]={name}.png.0.0
BackImage[2][0][0][0][0]={name}.png.0.0
BackImage[3][0][0][0][0]={name}.png.0.0
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_url")
    parser.add_argument("entry_dir")
    parser.add_argument("name")
    args = parser.parse_args()

    workdir = os.path.join(BASE, args.name)
    print(f"[1/6] fetching building assets -> {workdir}")
    obj_path = fetch_building(args.zip_url, args.entry_dir, workdir)

    print("[2/6] computing footprint")
    span_x, span_y, span_z = compute_footprint(obj_path)
    print(f"  footprint: x={span_x:.1f}m y={span_y:.1f}m height={span_z:.1f}m")

    building_png = os.path.join(workdir, f"{args.name}.png")
    print("[3/6] rendering via Blender headless")
    render_building(obj_path, building_png)

    icon_png = os.path.join(workdir, f"{args.name}_icon.png")
    print("[4/6] compositing icon")
    make_icon(building_png, icon_png)

    dat_path = os.path.join(workdir, f"{args.name}.dat")
    print("[5/6] writing dat")
    with open(dat_path, "w", encoding="utf-8") as f:
        f.write(DAT_TEMPLATE.format(name=args.name))

    print("[6/6] lint + makeobj")
    subprocess.run(["dat_linter", "lint", dat_path], check=True)
    pak_path = os.path.join(workdir, f"{args.name}.pak")
    subprocess.run(
        ["makeobj", "pak128", pak_path, os.path.basename(dat_path)],
        cwd=workdir, check=True,
    )
    print(f"DONE: {pak_path}")


if __name__ == "__main__":
    main()
