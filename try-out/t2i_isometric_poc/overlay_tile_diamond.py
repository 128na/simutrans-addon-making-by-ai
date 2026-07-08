"""
「ベースタイル菱形」(幅=画像幅, 高さ=画像幅/2, 画像下端に接地)の輪郭線を
任意の画像に重ね描きして、建物の接地面とタイル境界がどれだけ一致しているかを
目視確認するための可視化ツール。

菱形の位置定義は diag_tile_marker.py で実測したキャリブレーション
（ortho_scale=sqrt(2), sensor_fit=HORIZONTAL, shift_y=0.25 のとき、
1x1 BUの地面タイルが「画像下端に接地・全幅を使う菱形」として投影される）
と、try-out/t2i_inpaint_poc/crop.png のタイル菱形定義（128x128キャンバスで
同じ比率）に基づく。

Usage:
    python overlay_tile_diamond.py <input.png> [output.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

LINE_COLOR = (0, 255, 255, 255)  # シアン、背景色と衝突しにくい
LINE_WIDTH = 3


def diamond_points(w: int, h: int) -> list[tuple[float, float]]:
    """幅w, 高さhの画像に対する「幅=w, 高さ=w/2, 下端接地」の菱形の4頂点を返す。"""
    dh = w / 2
    top = (w / 2, h - 1 - dh)
    right = (w - 1, h - 1 - dh / 2)
    bottom = (w / 2, h - 1)
    left = (0, h - 1 - dh / 2)
    return [top, right, bottom, left]


def overlay(src_path: Path, dst_path: Path) -> None:
    img = Image.open(src_path).convert("RGBA")
    w, h = img.size
    overlay_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_img)
    pts = diamond_points(w, h)
    draw.line(pts + [pts[0]], fill=LINE_COLOR, width=LINE_WIDTH, joint="curve")
    combined = Image.alpha_composite(img, overlay_img)
    combined.save(dst_path)
    print(f"[overlay_tile_diamond] {src_path.name} ({w}x{h}) -> {dst_path.name}")
    print(f"  diamond points: {pts}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python overlay_tile_diamond.py <input.png> [output.png]")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_diamond_overlay.png")
    overlay(src, dst)


if __name__ == "__main__":
    main()
