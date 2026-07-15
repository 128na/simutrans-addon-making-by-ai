"""
Blenderで4倍解像度(512x512)レンダリングした"_raw.png"を128x128に縮小し、
アルファ値を0/255の二値にハード閾値処理する後処理スクリプト。

タイル境界(平面の外周)がアンチエイリアスでそのまま半透明ピクセルになると、
Simutrans上でタイルを連続設置したときに隙間として見えてしまう問題への対策
（ユーザー実機確認で指摘）。LANCZOSで縮小してなめらかな輪郭を保ちつつ、
最後にアルファを二値化することで半透明ピクセルを一切残さない。

上記だけだと今度は境界に色みの差（明るい/暗いフリンジ）が出る問題が別途見つかった。
原因は2つ重なっていた:
1. 透明領域のRGBはBlenderの背景色である黒(0,0,0)のまま保存されており、
   「不透明な物体色」と「透明領域の黒」を混ぜるとリンギングが生じる
   → 縮小前に透明領域のRGBを最も近い不透明ピクセルの色で塗りつぶす(color bleed/dilate)
2. それでも直らなかった。原因はPillowの`Image.resize`がRGBA画像に対して
   アルファを考慮した特殊処理を内部で行っており、RGBだけ塗りつぶしても
   RGBAのまま一括でresizeするとその内部処理でフリンジが再発する
   → RGB(3ch)とアルファ(グレースケール1ch)を完全に別画像として個別にresizeし、
     最後に合成することで解消（`rgb_img.resize(...)`と`alpha_img.resize(...)`を分離）

Usage:
    python postprocess.py
"""

import os
import numpy as np
from PIL import Image

TARGET_SIZE = 128
ALPHA_THRESHOLD = 128  # これ未満は透明(0)、以上は不透明(255)
DILATE_ITERATIONS = 16  # 512px解像度で16px分色を滲ませる（128縮小後で約4px相当）

_NEIGHBOR_OFFSETS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]

# (raw入力ファイル名, 最終出力ファイル名, アルファ二値化+カラーブリードするか)
FILES = [
    ("road_flat_raw.png", "road_flat.png", True),
    ("road_icon_raw.png", "road_icon.png", False),
    ("rail_flat_raw.png", "rail_flat.png", True),
    ("rail_icon_raw.png", "rail_icon.png", False),
]


def dilate_color(rgb, known_mask, iterations):
    """透明領域のRGBを近傍の既知(不透明)ピクセルの色で塗りつぶす。"""
    rgb = rgb.astype(np.float32).copy()
    mask = known_mask.copy()
    for _ in range(iterations):
        unknown = ~mask
        if not unknown.any():
            break
        sum_rgb = np.zeros_like(rgb)
        count = np.zeros(mask.shape, dtype=np.float32)
        for dy, dx in _NEIGHBOR_OFFSETS:
            shifted_mask = np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
            shifted_rgb = np.roll(np.roll(rgb, dy, axis=0), dx, axis=1)
            contrib = shifted_mask & unknown
            sum_rgb[contrib] += shifted_rgb[contrib]
            count[contrib] += 1
        newly_filled = unknown & (count > 0)
        rgb[newly_filled] = sum_rgb[newly_filled] / count[newly_filled][:, None]
        mask = mask | newly_filled
    return rgb


def process(raw_name, out_name, is_way_image):
    base_dir = os.path.dirname(__file__)
    raw_path = os.path.join(base_dir, raw_name)
    out_path = os.path.join(base_dir, out_name)

    if not is_way_image:
        img = Image.open(raw_path).convert("RGB")
        img = img.resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)
        img.save(out_path)
        print(f"POSTPROCESS_DONE: {raw_name} -> {out_name} ({img.size[0]}x{img.size[1]})")
        return

    arr = np.array(Image.open(raw_path).convert("RGBA"))
    rgb, alpha = arr[:, :, :3], arr[:, :, 3]
    bled_rgb = dilate_color(rgb, alpha > 0, DILATE_ITERATIONS).clip(0, 255).astype(np.uint8)

    # RGBとアルファは完全に別画像としてresizeする（一括RGBAでresizeすると
    # PillowのRGBA向け内部処理でフリンジが再発するため。詳細は上のコメント参照）
    rgb_img = Image.fromarray(bled_rgb, "RGB").resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)
    alpha_img = Image.fromarray(alpha, "L").resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)
    alpha_img = alpha_img.point(lambda v: 255 if v >= ALPHA_THRESHOLD else 0)

    r, g, b = rgb_img.split()
    img = Image.merge("RGBA", (r, g, b, alpha_img))
    img.save(out_path)
    print(f"POSTPROCESS_DONE: {raw_name} -> {out_name} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    for raw_name, out_name, is_way_image in FILES:
        process(raw_name, out_name, is_way_image)
