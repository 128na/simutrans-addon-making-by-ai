"""v5派生: 段階的denoiseマスク(v5)に加え、ControlNet(canny)へ「入口からタイル境界頂点まで伸びる
ガイド線」を明示的に与える案(フィードバック対応その3の代替アプローチ2)。

v4で「ControlNet(canny)除去」が装飾生成のブレイクスルーだったため、本アプローチはその方針とは
逆行するが、「通路のような連続性が重要な構造物にはControlNetでの構図誘導が効くかもしれない」という
仮説を検証する目的で、prepare_canvas_v5.pyのsilhouette(建物シルエットのみ)に、入口点から
タイル境界頂点(exit_point)まで伸びる太めの線を追加で描き足す。ControlNet strengthは低め
(0.2〜0.3程度)で運用し、v3で判明した「エッジなし=生成抑制」バイアスを避けつつ、線の方向だけを
弱く誘導することを狙う。

使い方:
    python prepare_canvas_v5_guideline.py
    その後 output/t2ipoc_v5g_*.png を E:\\ComfyUI\\input\\ に t2ipoc_canvas.png / t2ipoc_mask.png /
    t2ipoc_silhouette.png としてコピーしてから
    run_inpaint.py --controlnet-strength 0.25 で実行する(strengthは要調整)。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from entrance_geometry import exit_point, find_entrance_point, load_masks
from prepare_canvas_v4 import BBOX_X0, BBOX_Y0, GEN_WIDTH
from prepare_canvas_v5 import EXIT_VERTEX_NAME, build_canvas_and_masks, graduated_mask

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

GUIDE_LINE_WIDTH = 10  # gen(1024幅)座標系での線の太さ(px)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas, generate_np, building_binary_np, scale, gen_w, gen_h, entrance_gen = build_canvas_and_masks()
    mask = graduated_mask(generate_np, gen_w, gen_h, entrance_gen, scale)

    building_alpha_full, diamond_full = load_masks(
        SCRIPT_DIR.parent / "plateau_building" / "building.png", SCRIPT_DIR / "crop.png"
    )
    exitp = exit_point(diamond_full, EXIT_VERTEX_NAME)
    ex_gen, ey_gen = entrance_gen
    exit_gen = ((exitp[0] - BBOX_X0) * scale, (exitp[1] - BBOX_Y0) * scale)

    silhouette_np = (building_binary_np * 255).astype(np.uint8)
    silhouette_img = Image.fromarray(silhouette_np, mode="L")
    draw = ImageDraw.Draw(silhouette_img)
    draw.line([(ex_gen, ey_gen), exit_gen], fill=255, width=GUIDE_LINE_WIDTH)
    silhouette = Image.merge("RGB", (silhouette_img, silhouette_img, silhouette_img))

    canvas.save(OUTPUT_DIR / "t2ipoc_v5g_canvas.png")
    mask.save(OUTPUT_DIR / "t2ipoc_v5g_mask.png")
    silhouette.save(OUTPUT_DIR / "t2ipoc_v5g_silhouette.png")

    print(f"[prepare_canvas_v5_guideline] entrance_gen=({ex_gen:.1f},{ey_gen:.1f}) "
          f"exit_gen=({exit_gen[0]:.1f},{exit_gen[1]:.1f}) line_width={GUIDE_LINE_WIDTH}")
    print(f"[prepare_canvas_v5_guideline] saved: {OUTPUT_DIR / 't2ipoc_v5g_canvas.png'}")
    print(f"[prepare_canvas_v5_guideline] saved: {OUTPUT_DIR / 't2ipoc_v5g_mask.png'}")
    print(f"[prepare_canvas_v5_guideline] saved: {OUTPUT_DIR / 't2ipoc_v5g_silhouette.png'}")
    print("[prepare_canvas_v5_guideline] 次に output/t2ipoc_v5g_*.png を E:\\ComfyUI\\input\\ へ "
          "t2ipoc_canvas.png/t2ipoc_mask.png/t2ipoc_silhouette.pngとしてコピーしてから "
          "run_inpaint.py --controlnet-strength 0.25 で実行すること")


if __name__ == "__main__":
    main()
