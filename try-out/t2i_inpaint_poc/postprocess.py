"""SDXL生成結果(1024x1024)を最終タイル(256x256、タイルの単純2倍拡大)へダウンスケールし、
(1) crop.pngが示す菱形の外側(四隅)を透明化し、
(2) 元の建物レイヤーを最上位に貼り戻して建物ピクセルを完全に保護する後処理。

## フィードバック対応(2026-07-08): crop.pngによる菱形クリップ + マージン廃止(v3)

v1では生成結果(256x256)をそのまま最終画像として使っていたが、実際にゲーム内で地面として
描画されるのはpak128の2:1菱形部分のみで、正方形画像の四隅は表示されない領域のため、
v2以降は生成結果を「菱形の外は透明」にクリップしてから建物を貼り戻す。
またv2で「外側マージンを残したままマスクだけ菱形に絞ると、グレーの保護領域(マージン+四隅)が
コンテキストの大半を占め、生成対象(菱形)まで単色グレーに引きずられる」問題が判明したため、
v3では`prepare_canvas.py`側でマージンを廃止(タイル自体を単純拡大する構成に変更)した。
本スクリプトもそれに合わせ、building.png/crop.pngを最終解像度へ直接リサイズする方式に変更している
(旧v1/v2の「128x128を256x256キャンバスの中央に配置」ではなく「128x128を256x256へ拡大」)。

処理手順:
1. 生成結果(1024x1024)をLanczosで256x256にダウンスケール
2. crop.png(128x128, 透明=菱形/青=四隅)を256x256にNEARESTリサイズしてから反転し、
   アルファステンシルを作る → 菱形の外側(四隅)を完全透明にする
3. building.png(128x128 RGBA)を256x256にLanczosリサイズしたうえでalpha_compositeで貼り戻す
   → 建物のアルファ値に応じて、建物ピクセルは(リサイズ由来の丸め誤差を除き)ほぼ元通りになり、
     境界のアンチエイリアス部分は元建物とSDXL生成背景がなめらかにブレンドされる
     (建物は菱形の外(屋根など)にはみ出していてもそのまま保護される)

使い方:
    python postprocess.py output/t2ipoc_inpaint_seed42_00004_.png
    python postprocess.py output/t2ipoc_inpaint_seed*.png   (シェル展開で複数可)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_BUILDING = SCRIPT_DIR.parent / "plateau_building" / "building.png"
INPUT_CROP = SCRIPT_DIR / "crop.png"
OUTPUT_DIR = SCRIPT_DIR / "output"

FINAL_SIZE = 256
TILE_SIZE = 128


def _diamond_stencil(crop: Image.Image, size: int) -> Image.Image:
    """crop.png(128x128)から、size x sizeキャンバス用の可視領域アルファステンシルを作る。

    crop.pngは 透明(alpha=0)=菱形(可視にしたい), 青(alpha=255)=四隅(不可視にしたい) なので、
    sizeへNEARESTリサイズ(境界をぼかさない)したうえでアルファを反転(255-alpha)する。
    """
    crop_resized = crop.resize((size, size), Image.NEAREST)
    crop_alpha = np.array(crop_resized.split()[-1])
    visible = (255 - crop_alpha).astype(np.uint8)  # 菱形=255(可視), 青=0(不可視)
    return Image.fromarray(visible, mode="L")


def postprocess_one(gen_path: Path, building: Image.Image, crop: Image.Image) -> Path:
    gen = Image.open(gen_path).convert("RGBA")
    downscaled = gen.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)

    # 菱形の外側(四隅)を透明化
    stencil = _diamond_stencil(crop, FINAL_SIZE)
    ground_layer = downscaled.convert("RGB").convert("RGBA")
    ground_layer.putalpha(stencil)

    # 透明キャンバス上にground_layerを合成し、最後に建物(拡大)を最上位に貼り戻す
    building_resized = building.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)
    final = Image.new("RGBA", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0, 0))
    final.alpha_composite(ground_layer)
    final.alpha_composite(building_resized)

    out_path = OUTPUT_DIR / f"final_{gen_path.stem}.png"
    final.save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="生成結果の後処理(ダウンスケール+菱形クリップ+建物貼り戻し)")
    parser.add_argument("inputs", nargs="+", type=Path, help="SDXL生成結果(1024x1024)のパス")
    args = parser.parse_args()

    building = Image.open(INPUT_BUILDING).convert("RGBA")
    assert building.size == (TILE_SIZE, TILE_SIZE)
    crop = Image.open(INPUT_CROP).convert("RGBA")
    assert crop.size == (TILE_SIZE, TILE_SIZE)

    for gen_path in args.inputs:
        if not gen_path.exists():
            print(f"[postprocess] skip (not found): {gen_path}", file=sys.stderr)
            continue
        out_path = postprocess_one(gen_path, building, crop)
        print(f"[postprocess] saved: {out_path}")


if __name__ == "__main__":
    main()
