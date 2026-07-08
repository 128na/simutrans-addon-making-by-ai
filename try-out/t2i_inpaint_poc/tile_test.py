"""最終タイル画像(256x256)を2x2に並べ、隣接タイルとの継ぎ目の破綻具合を目視確認するための画像を作る。

注意: 今回のワークフローはタイル境界をシームレスにする設計にはなっていない
(各生成は独立しており、左右上下の端が一致する保証はない)。あくまで
「現状どの程度不自然に見えるか」の一次評価用。

使い方:
    python tile_test.py output/final_t2ipoc_inpaint_seed42_00002_.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"


def main() -> None:
    parser = argparse.ArgumentParser(description="256x256タイルを2x2に並べて継ぎ目を確認する")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    tile = Image.open(args.input).convert("RGBA")
    w, h = tile.size
    grid = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 255))
    for gy in range(2):
        for gx in range(2):
            grid.paste(tile, (gx * w, gy * h))

    out_path = OUTPUT_DIR / f"tiled2x2_{args.input.stem}.png"
    grid.save(out_path)
    print(f"[tile_test] saved: {out_path}")


if __name__ == "__main__":
    main()
