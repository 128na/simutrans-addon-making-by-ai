"""
0series_s.png (s方向レンダー) から ControlNet-canny 用のedge画像を抽出する。

try-out/t2i_isometric_poc/preprocess_edges_depth.py の make_canny() をそのまま流用。
白背景合成 → グレースケール → Canny → SDXL生成解像度(1024x1024)にリサイズして保存する。

Usage:
    python preprocess_canny.py
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SRC_PATH = SCRIPT_DIR / "0series_s.png"
CANNY_PATH = OUTPUT_DIR / "0series_s_canny.png"
CANNY_1024_PATH = OUTPUT_DIR / "0series_s_canny_1024.png"
COLOR_1024_PATH = OUTPUT_DIR / "0series_s_render_1024.png"  # 参考比較用

GEN_SIZE = 1024


def load_rgba(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    return np.array(img)


def composite_on_white(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = (rgba[:, :, 3:4].astype(np.float32)) / 255.0
    white = np.ones_like(rgb) * 255.0
    out = rgb * alpha + white * (1 - alpha)
    return out.astype(np.uint8)


def make_canny(rgb_on_white: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb_on_white, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 60, 150)
    return edges


def main() -> None:
    rgba = load_rgba(SRC_PATH)
    w, h = rgba.shape[1], rgba.shape[0]
    print(f"[main] input: {SRC_PATH.name} ({w}x{h})")

    rgb_on_white = composite_on_white(rgba)

    canny = make_canny(rgb_on_white)
    canny_img = Image.fromarray(canny).convert("L")
    canny_img.save(CANNY_PATH)
    # 元解像度が512と十分あるためLANCZOSアップサンプルで線を滑らかにする
    # (128x128起点だったisometric_pocのNEARESTと異なり、今回は512起点なので補間で問題ない)
    canny_img.resize((GEN_SIZE, GEN_SIZE), Image.LANCZOS).save(CANNY_1024_PATH)
    print(f"[canny] saved: {CANNY_PATH}, {CANNY_1024_PATH}")

    Image.fromarray(rgb_on_white).resize((GEN_SIZE, GEN_SIZE), Image.LANCZOS).save(COLOR_1024_PATH)
    print(f"[color_1024] saved: {COLOR_1024_PATH}")


if __name__ == "__main__":
    main()
