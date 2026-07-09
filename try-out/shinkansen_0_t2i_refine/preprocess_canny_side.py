"""
0series_side_elevation.png (真の側面図レンダー, 仰角0°) から ControlNet-canny 用の
edge画像を抽出する。

preprocess_canny.py の make_canny()/composite_on_white() をそのまま再利用し、
出力ファイル名だけ側面図用に変える。

Usage:
    python preprocess_canny_side.py
"""
from pathlib import Path

from PIL import Image

from preprocess_canny import composite_on_white, load_rgba, make_canny

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SRC_PATH = SCRIPT_DIR / "0series_side_elevation.png"
CANNY_PATH = OUTPUT_DIR / "0series_side_elevation_canny.png"
CANNY_1024_PATH = OUTPUT_DIR / "0series_side_elevation_canny_1024.png"
COLOR_1024_PATH = OUTPUT_DIR / "0series_side_elevation_render_1024.png"  # 参考比較用

GEN_SIZE = 1024


def main() -> None:
    rgba = load_rgba(SRC_PATH)
    w, h = rgba.shape[1], rgba.shape[0]
    print(f"[main] input: {SRC_PATH.name} ({w}x{h})")

    rgb_on_white = composite_on_white(rgba)

    canny = make_canny(rgb_on_white)
    canny_img = Image.fromarray(canny).convert("L")
    canny_img.save(CANNY_PATH)
    canny_img.resize((GEN_SIZE, GEN_SIZE), Image.LANCZOS).save(CANNY_1024_PATH)
    print(f"[canny] saved: {CANNY_PATH}, {CANNY_1024_PATH}")

    Image.fromarray(rgb_on_white).resize((GEN_SIZE, GEN_SIZE), Image.LANCZOS).save(COLOR_1024_PATH)
    print(f"[color_1024] saved: {COLOR_1024_PATH}")


if __name__ == "__main__":
    main()
