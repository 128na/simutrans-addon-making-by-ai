"""v4(crop-and-zoom)の生成結果を最終タイル(256x256)へ合成する後処理。

prepare_canvas_v4.pyで生成したのはタイル全体ではなく、生成対象のバウンディングボックス
(BBOX_*、128タイル座標系)だけを切り出して拡大したキャンバスなので、通常のpostprocess.pyとは
異なり「生成結果をダウンスケール→bboxの位置に貼り戻す→菱形の外を透明化→建物を貼り戻す」
という手順になる。

使い方:
    python postprocess_v4.py output/t2ipoc_v4_full_seed42_00001_.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from prepare_canvas_v4 import BBOX_X0, BBOX_X1, BBOX_Y0, BBOX_Y1, INPUT_BUILDING, INPUT_CROP, TILE_SIZE

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

FINAL_SCALE = 2
FINAL_SIZE = TILE_SIZE * FINAL_SCALE  # 256


def postprocess_one(gen_path: Path, building: Image.Image, crop: Image.Image) -> Path:
    bb_h, bb_w = BBOX_Y1 - BBOX_Y0, BBOX_X1 - BBOX_X0
    final_bb_w, final_bb_h = bb_w * FINAL_SCALE, bb_h * FINAL_SCALE

    gen = Image.open(gen_path).convert("RGBA")
    gen_down = gen.resize((final_bb_w, final_bb_h), Image.LANCZOS)

    # bboxの位置に貼り戻し、それ以外は透明のまま
    ground_layer = Image.new("RGBA", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0, 0))
    ground_layer.paste(gen_down, (BBOX_X0 * FINAL_SCALE, BBOX_Y0 * FINAL_SCALE))

    # 菱形の外側(四隅)を透明化。bbox外では既にalpha=0なので、菱形ステンシルとbbox内alphaの
    # 小さい方(min)を取ることで「菱形内 かつ bbox内」だけを可視にする
    crop_resized = crop.resize((FINAL_SIZE, FINAL_SIZE), Image.NEAREST)
    crop_alpha = np.array(crop_resized.split()[-1])
    diamond_visible = (255 - crop_alpha).astype(np.uint8)
    existing_alpha = np.array(ground_layer.split()[-1])
    combined_alpha = np.minimum(diamond_visible, existing_alpha)

    ground_rgba = ground_layer.convert("RGB").convert("RGBA")
    ground_rgba.putalpha(Image.fromarray(combined_alpha, mode="L"))

    # 建物を最上位に貼り戻して保護
    building_resized = building.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)
    final = Image.new("RGBA", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0, 0))
    final.alpha_composite(ground_rgba)
    final.alpha_composite(building_resized)

    out_path = OUTPUT_DIR / f"final_{gen_path.stem}.png"
    final.save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="v4(crop-and-zoom)生成結果の後処理")
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    building = Image.open(INPUT_BUILDING).convert("RGBA")
    assert building.size == (TILE_SIZE, TILE_SIZE)
    crop = Image.open(INPUT_CROP).convert("RGBA")
    assert crop.size == (TILE_SIZE, TILE_SIZE)

    for gen_path in args.inputs:
        if not gen_path.exists():
            print(f"[postprocess_v4] skip (not found): {gen_path}", file=sys.stderr)
            continue
        out_path = postprocess_one(gen_path, building, crop)
        print(f"[postprocess_v4] saved: {out_path}")


if __name__ == "__main__":
    main()
