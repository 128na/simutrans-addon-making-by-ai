"""v5(段階的denoiseマスク)の生成結果を最終タイルへ合成する後処理。

v4のpostprocess_v4.pyとの違い: 建物を最上位に貼り戻す際、入口付近(prepare_canvas_v5と同じ
entrance point/半径)だけ建物のアルファを弱めて、生成された通路が建物にめり込む形でシームレスに
繋がっているように見せる。v5マスクで許可した「建物側のdenoise帯」は建物の不透明ピクセル内にも
存在するため、v4のように無条件で建物を全面貼り戻すと、その帯で生成された内容が完全に消えてしまう
(元の建物ピクセルで上書きされる)。本ファイルはその貼り戻しロジックを、入口付近だけ弱めるように
拡張する。

使い方:
    python postprocess_v5.py output/t2ipoc_v5_full_seed42_00001_.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from entrance_geometry import find_entrance_point, load_masks
from prepare_canvas_v4 import BBOX_X0, BBOX_X1, BBOX_Y0, BBOX_Y1, INPUT_BUILDING, INPUT_CROP, TILE_SIZE
from prepare_canvas_v5 import ENTRANCE_RADIUS_ORIG, EXIT_VERTEX_NAME

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

FINAL_SCALE = 2
FINAL_SIZE = TILE_SIZE * FINAL_SCALE


def postprocess_one(
    gen_path: Path, building: Image.Image, crop: Image.Image, entrance_orig: tuple[int, int]
) -> Path:
    bb_h, bb_w = BBOX_Y1 - BBOX_Y0, BBOX_X1 - BBOX_X0
    final_bb_w, final_bb_h = bb_w * FINAL_SCALE, bb_h * FINAL_SCALE

    gen = Image.open(gen_path).convert("RGBA")
    gen_down = gen.resize((final_bb_w, final_bb_h), Image.LANCZOS)

    ground_layer = Image.new("RGBA", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0, 0))
    ground_layer.paste(gen_down, (BBOX_X0 * FINAL_SCALE, BBOX_Y0 * FINAL_SCALE))

    crop_resized = crop.resize((FINAL_SIZE, FINAL_SIZE), Image.NEAREST)
    crop_alpha = np.array(crop_resized.split()[-1])
    diamond_visible = (255 - crop_alpha).astype(np.uint8)
    existing_alpha = np.array(ground_layer.split()[-1])
    combined_alpha = np.minimum(diamond_visible, existing_alpha)

    ground_rgba = ground_layer.convert("RGB").convert("RGBA")
    ground_rgba.putalpha(Image.fromarray(combined_alpha, mode="L"))

    # --- 建物を貼り戻す。ただし入口半径内は建物側アルファを弱め、生成された通路を透過させる ---
    building_resized = building.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)
    building_alpha = np.array(building_resized.split()[-1]).astype(np.float32)

    ex_final = entrance_orig[0] * FINAL_SCALE
    ey_final = entrance_orig[1] * FINAL_SCALE
    radius_final = ENTRANCE_RADIUS_ORIG * FINAL_SCALE

    yy, xx = np.mgrid[0:FINAL_SIZE, 0:FINAL_SIZE]
    dist = np.sqrt((xx - ex_final) ** 2 + (yy - ey_final) ** 2)
    g = np.clip(1.0 - dist / radius_final, 0.0, 1.0)  # 1=入口中心(建物を最も透過), 0=半径外(完全保護)

    faded_alpha = building_alpha * (1.0 - g)
    building_faded = building_resized.copy()
    building_faded.putalpha(Image.fromarray(np.clip(faded_alpha, 0, 255).astype(np.uint8), mode="L"))

    final = Image.new("RGBA", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0, 0))
    final.alpha_composite(ground_rgba)
    final.alpha_composite(building_faded)

    out_path = OUTPUT_DIR / f"final_{gen_path.stem}.png"
    final.save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="v5(段階的denoiseマスク)生成結果の後処理")
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    building = Image.open(INPUT_BUILDING).convert("RGBA")
    assert building.size == (TILE_SIZE, TILE_SIZE)
    crop = Image.open(INPUT_CROP).convert("RGBA")
    assert crop.size == (TILE_SIZE, TILE_SIZE)

    building_alpha_full, diamond_full = load_masks(INPUT_BUILDING, INPUT_CROP)
    entrance_orig = find_entrance_point(building_alpha_full, diamond_full, EXIT_VERTEX_NAME)

    for gen_path in args.inputs:
        if not gen_path.exists():
            print(f"[postprocess_v5] skip (not found): {gen_path}", file=sys.stderr)
            continue
        out_path = postprocess_one(gen_path, building, crop, entrance_orig)
        print(f"[postprocess_v5] saved: {out_path}")


if __name__ == "__main__":
    main()
