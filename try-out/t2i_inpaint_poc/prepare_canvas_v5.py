"""v5: 建物入口とタイル境界間を通路で連続接続するための段階的denoiseマスク。

## フィードバック対応その3(2026-07-09): 通路を建物入口とタイル境界間で連続接続

v4までは建物シルエットを常にdenoise=0(完全保護)としていたため、生成される通路・花壇は
「隙間(三日月)の中だけで完結」し、建物のどこかから連続的に始まっているようには見えなかった
(建物と生成領域の境界は常に貼り戻しでスパッと切れる)。

本v5では、entrance_geometry.find_entrance_point()で近似推定した入口付近だけ、建物シルエット側に
半径ENTRANCE_RADIUS_ORIG(px, 128タイル座標系)のグラデーション帯を設け、denoiseを0(完全保護)から
BAND_TARGET_DENOISE(既定0.42、指示範囲0.3〜0.5内)まで滑らかに持ち上げる。それ以外の建物部分は
v4と同じく完全保護(denoise=0)のまま。

crop-and-zoom(v4)・ControlNet除去(v4)は維持し、マスク生成のみ拡張する。
(ControlNetガイド線を併用する場合は prepare_canvas_v5_guideline.py を使う)

使い方:
    python prepare_canvas_v5.py
    その後 output/t2ipoc_v5_*.png を E:\\ComfyUI\\input\\ に t2ipoc_canvas.png / t2ipoc_mask.png /
    t2ipoc_silhouette.png としてコピーしてから run_inpaint.py --controlnet-strength 0.0 で実行する。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from entrance_geometry import exit_point, find_entrance_point, load_masks
from prepare_canvas_v4 import (
    ALPHA_THRESHOLD,
    BBOX_X0,
    BBOX_X1,
    BBOX_Y0,
    BBOX_Y1,
    GEN_WIDTH,
    INPUT_BUILDING,
    INPUT_CROP,
    MASK_DILATE_PX_BASE,
)

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

# 入口帯のパラメータ(128タイル座標系)。「数px〜十数px幅」の指示に合わせた半径。
ENTRANCE_RADIUS_ORIG = 16
# 帯の中心(入口の建物境界上)でのdenoise強度目安。指示範囲(0.3〜0.5)内。
BAND_TARGET_DENOISE = 0.42
EXIT_VERTEX_NAME = "bottom"  # 通路が向かう先の菱形頂点(南、カメラ手前側)


def build_canvas_and_masks() -> tuple[Image.Image, np.ndarray, np.ndarray, float, int, int, tuple[int, int]]:
    """v4と共通のcrop-and-zoomキャンバスを作り、入口点(gen座標系)も合わせて返す。"""
    building = Image.open(INPUT_BUILDING).convert("RGBA")
    crop = Image.open(INPUT_CROP).convert("RGBA")

    building_alpha_full, diamond_full = load_masks(INPUT_BUILDING, INPUT_CROP)
    entrance = find_entrance_point(building_alpha_full, diamond_full, EXIT_VERTEX_NAME)
    exitp = exit_point(diamond_full, EXIT_VERTEX_NAME)
    print(f"[prepare_canvas_v5] entrance(orig)={entrance} exit_vertex(orig)={exitp}")

    bb_h, bb_w = BBOX_Y1 - BBOX_Y0, BBOX_X1 - BBOX_X0
    building_crop = building.crop((BBOX_X0, BBOX_Y0, BBOX_X1, BBOX_Y1))
    crop_crop = crop.crop((BBOX_X0, BBOX_Y0, BBOX_X1, BBOX_Y1))

    scale = GEN_WIDTH / bb_w
    gen_w = GEN_WIDTH
    gen_h = int(round(bb_h * scale / 8) * 8)

    building_gen = building_crop.resize((gen_w, gen_h), Image.LANCZOS)
    crop_gen = crop_crop.resize((gen_w, gen_h), Image.NEAREST)

    canvas_rgba = Image.new("RGBA", (gen_w, gen_h), (127, 127, 127, 255))
    canvas_rgba.alpha_composite(building_gen, dest=(0, 0))
    canvas = canvas_rgba.convert("RGB")

    alpha = building_gen.split()[-1]
    building_binary = alpha.point(lambda a: 255 if a >= ALPHA_THRESHOLD else 0)
    dilate_px = round(MASK_DILATE_PX_BASE * scale)
    k = dilate_px * 2 + 1
    protect_eroded = building_binary.filter(ImageFilter.MinFilter(k))

    crop_alpha = crop_gen.split()[-1]
    diamond_binary = crop_alpha.point(lambda a: 255 if a == 0 else 0)

    diamond_np = np.array(diamond_binary) > 0
    protect_np = np.array(protect_eroded) > 0
    generate_np = diamond_np & ~protect_np  # v4と同じ基本マスク(bool)

    ex_gen = (entrance[0] - BBOX_X0) * scale
    ey_gen = (entrance[1] - BBOX_Y0) * scale

    return canvas, generate_np, np.array(building_binary) > 0, scale, gen_w, gen_h, (ex_gen, ey_gen)


def graduated_mask(generate_np: np.ndarray, gen_w: int, gen_h: int, entrance_gen: tuple[float, float], scale: float) -> Image.Image:
    ex_gen, ey_gen = entrance_gen
    radius_gen = ENTRANCE_RADIUS_ORIG * scale

    yy, xx = np.mgrid[0:gen_h, 0:gen_w]
    dist = np.sqrt((xx - ex_gen) ** 2 + (yy - ey_gen) ** 2)
    g = np.clip(1.0 - dist / radius_gen, 0.0, 1.0)  # 1=入口中心, 0=半径外

    mask_f = generate_np.astype(np.float32) * 255.0
    band_value = BAND_TARGET_DENOISE * 255.0
    protect_side = ~generate_np
    # 建物側(protect)のうち入口半径内だけ持ち上げる。generate側(crescent)は常に255のまま変更しない。
    mask_f = np.where(protect_side, band_value * g, mask_f)
    return Image.fromarray(np.clip(mask_f, 0, 255).astype(np.uint8), mode="L")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas, generate_np, building_binary_np, scale, gen_w, gen_h, entrance_gen = build_canvas_and_masks()

    mask = graduated_mask(generate_np, gen_w, gen_h, entrance_gen, scale)
    silhouette_np = (building_binary_np * 255).astype(np.uint8)
    silhouette = Image.merge("RGB", tuple(Image.fromarray(silhouette_np, mode="L") for _ in range(3)))

    canvas.save(OUTPUT_DIR / "t2ipoc_v5_canvas.png")
    mask.save(OUTPUT_DIR / "t2ipoc_v5_mask.png")
    silhouette.save(OUTPUT_DIR / "t2ipoc_v5_silhouette.png")

    print(f"[prepare_canvas_v5] gen_size=({gen_w},{gen_h}) entrance_gen=({entrance_gen[0]:.1f},{entrance_gen[1]:.1f}) "
          f"radius_gen={ENTRANCE_RADIUS_ORIG * scale:.1f} band_target_denoise={BAND_TARGET_DENOISE}")
    print(f"[prepare_canvas_v5] saved: {OUTPUT_DIR / 't2ipoc_v5_canvas.png'}")
    print(f"[prepare_canvas_v5] saved: {OUTPUT_DIR / 't2ipoc_v5_mask.png'}")
    print(f"[prepare_canvas_v5] saved: {OUTPUT_DIR / 't2ipoc_v5_silhouette.png'}")
    print("[prepare_canvas_v5] 次に output/t2ipoc_v5_*.png を E:\\ComfyUI\\input\\ へ "
          "t2ipoc_canvas.png/t2ipoc_mask.png/t2ipoc_silhouette.pngとしてコピーしてから "
          "run_inpaint.py --controlnet-strength 0.0 で実行すること")


if __name__ == "__main__":
    main()
