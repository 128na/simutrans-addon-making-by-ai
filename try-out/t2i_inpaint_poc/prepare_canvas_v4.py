"""v4: 生成対象のバウンディングボックスだけを切り出して拡大する(crop-and-zoom)キャンバス生成。

## フィードバック対応その2(2026-07-08): 面積制約に適した小物生成への方針転換

v3(`prepare_canvas.py`)まではタイル全体(128x128)を8倍拡大した1024x1024キャンバスで生成していたが、
保護領域(建物+四隅)がタイルの約98%を占め、生成対象(菱形-建物)が約7%の細い三日月状にしかならない
ため、SDXLがほぼ無地グレーしか生成しない問題が判明していた（README「フィードバック対応」節参照）。

ユーザーからの追加フィードバックで「面積が狭いこと自体は問題ではなく、通路・花壇・ベンチのような
小さな離散オブジェクトを配置したい」という目的が明確になったため、本v4では以下2点を変更する。

1. **crop-and-zoom**: 生成対象(diamond-minus-building)のバウンディングボックスだけを切り出し、
   その範囲を1024pxの横幅に合わせて拡大する。今回のbuilding.png/crop.pngでは
   bbox = y[61:128], x[0:128] (128タイル座標系、侵食分4pxの余白を含む)で、
   生成対象比率がタイル全体基準の約7%から、bbox内基準で約19%まで向上する
2. **ControlNet(canny)を外す**: v3までは建物シルエットの輪郭誘導にControlNet(canny)を
   使っていたが、生成対象領域がほぼ全域にわたって「エッジなし(黒)」の条件になるため、
   ControlNetが「新しい物体を生成しない」方向に働いてしまう可能性が実験的に確認された
   (`--controlnet-strength 0.6`→`0.0`の比較で明確な差が出た)。本v4はControlNetなし
   (`run_inpaint.py --controlnet-strength 0.0`)で運用する。建物保護は引き続き貼り戻しで
   担保されるため、ControlNetによる建物輪郭の拘束がなくてもRAW生成時点での建物の
   多少の再解釈は最終結果に影響しない

使い方:
    python prepare_canvas_v4.py
    その後 output/t2ipoc_canvas.png 等を E:\\ComfyUI\\input\\ にコピーしてから
    run_inpaint.py --controlnet-strength 0.0 --prompt "..." で生成する。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_BUILDING = SCRIPT_DIR.parent / "plateau_building" / "building.png"
INPUT_CROP = SCRIPT_DIR / "crop.png"
OUTPUT_DIR = SCRIPT_DIR / "output"

TILE_SIZE = 128
MASK_DILATE_PX_BASE = 3  # 128x128タイル基準の保護領域侵食量(v3と同じ考え方)
ALPHA_THRESHOLD = 10

# 生成対象(diamond-minus-building)のバウンディングボックス(128タイル座標系)。
# building.png/crop.pngの実データから算出した固定値(このPoCでは1建物のみのため決め打ち)。
# 侵食(MASK_DILATE_PX_BASE)分の余白を含めて y=61からを対象にしている。
BBOX_Y0, BBOX_Y1 = 61, 128
BBOX_X0, BBOX_X1 = 0, 128

GEN_WIDTH = 1024  # SDXLネイティブ解像度に合わせる横幅


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    building = Image.open(INPUT_BUILDING).convert("RGBA")
    assert building.size == (TILE_SIZE, TILE_SIZE)
    crop = Image.open(INPUT_CROP).convert("RGBA")
    assert crop.size == (TILE_SIZE, TILE_SIZE)

    bb_h, bb_w = BBOX_Y1 - BBOX_Y0, BBOX_X1 - BBOX_X0
    building_crop = building.crop((BBOX_X0, BBOX_Y0, BBOX_X1, BBOX_Y1))
    crop_crop = crop.crop((BBOX_X0, BBOX_Y0, BBOX_X1, BBOX_Y1))

    scale = GEN_WIDTH / bb_w
    gen_w = GEN_WIDTH
    gen_h = int(round(bb_h * scale / 8) * 8)  # SDXL latentのため8の倍数に丸める

    building_gen = building_crop.resize((gen_w, gen_h), Image.LANCZOS)
    crop_gen = crop_crop.resize((gen_w, gen_h), Image.NEAREST)

    # --- canvas: 中間グレー背景 + 建物をアルファ合成 ---
    canvas_rgba = Image.new("RGBA", (gen_w, gen_h), (127, 127, 127, 255))
    canvas_rgba.alpha_composite(building_gen, dest=(0, 0))
    canvas = canvas_rgba.convert("RGB")

    # --- 建物の保護領域 ---
    alpha = building_gen.split()[-1]
    building_binary = alpha.point(lambda a: 255 if a >= ALPHA_THRESHOLD else 0)
    dilate_px = round(MASK_DILATE_PX_BASE * scale)
    k = dilate_px * 2 + 1
    protect_eroded = building_binary.filter(ImageFilter.MinFilter(k))

    # --- 菱形の生成候補領域 ---
    crop_alpha = crop_gen.split()[-1]
    diamond_binary = crop_alpha.point(lambda a: 255 if a == 0 else 0)

    diamond_np = np.array(diamond_binary) > 0
    protect_np = np.array(protect_eroded) > 0
    generate_np = diamond_np & ~protect_np
    mask = Image.fromarray((generate_np * 255).astype(np.uint8), mode="L")

    # --- silhouette: ワークフローのグラフ構成上LoadImageノードが参照するため生成しておく。
    #     ただしControlNet strength=0で運用するため、実質的に生成結果へ影響しない ---
    silhouette = Image.merge("RGB", (building_binary, building_binary, building_binary))

    canvas.save(OUTPUT_DIR / "t2ipoc_canvas.png")
    mask.save(OUTPUT_DIR / "t2ipoc_mask.png")
    silhouette.save(OUTPUT_DIR / "t2ipoc_silhouette.png")

    print(f"[prepare_canvas_v4] bbox=({BBOX_X0},{BBOX_Y0})-({BBOX_X1},{BBOX_Y1}) "
          f"gen_size=({gen_w},{gen_h}) generate_ratio={generate_np.mean():.3f}")
    print(f"[prepare_canvas_v4] saved: {OUTPUT_DIR / 't2ipoc_canvas.png'}")
    print(f"[prepare_canvas_v4] saved: {OUTPUT_DIR / 't2ipoc_mask.png'}")
    print(f"[prepare_canvas_v4] saved: {OUTPUT_DIR / 't2ipoc_silhouette.png'}")
    print("[prepare_canvas_v4] 次に output/t2ipoc_*.png を E:\\ComfyUI\\input\\ へコピーしてから "
          "run_inpaint.py --controlnet-strength 0.0 で実行すること")


if __name__ == "__main__":
    main()
