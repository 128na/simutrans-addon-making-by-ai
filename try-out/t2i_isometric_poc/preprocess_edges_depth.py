"""
Blenderレンダリング画像から ControlNet 条件入力用の canny edge / 簡易depth proxy を抽出する。

- canny: OpenCVのCanny edge detectorを、アルファ合成済み(白背景)のグレースケール画像に適用。
  ControlNet-cannyはSDXL用でも入力解像度を選ばないため、そのままではなく
  SDXL標準の1024x1024にリサイズしたバージョンも保存する（生成側の解像度に合わせるため）。
- depth: 本格的なmonocular depth推定モデル（ZoeDepth等）は今回のPoCでは導入コストに見合わないと
  判断し見送った。代わりにアルファチャンネルのシルエットに distance transform を適用した
  簡易プロキシ（シルエット中心に近いほど白=近い、輪郭に近いほど黒=遠い、という疑似的な立体感）を
  depth ControlNetの入力として使う。実カメラ距離とは異なる近似値である点に注意。

Usage:
    python preprocess_edges_depth.py
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

SRC_PATH = OUTPUT_DIR / "building_render.png"
CANNY_PATH = OUTPUT_DIR / "building_canny.png"
CANNY_1024_PATH = OUTPUT_DIR / "building_canny_1024.png"
DEPTH_PATH = OUTPUT_DIR / "building_depth_proxy.png"
DEPTH_1024_PATH = OUTPUT_DIR / "building_depth_proxy_1024.png"
COLOR_1024_PATH = OUTPUT_DIR / "building_render_1024.png"  # 参考比較用（アルファ合成・白背景）

# 2026-07-08 フィードバック対応: building_render.py がタイル整合キャリブレーション
# (256x384, ortho_scale=sqrt(2)) に変更されたため、入力画像のアスペクト比(2:3)を
# 保ったままSDXL bucket解像度に合わせた生成用サイズを別途用意する。
# 832x1248 = 256x384 を正確に3.25倍（8の倍数を維持、2:3比率を厳密に保持）
CANNY_GEN_PATH = OUTPUT_DIR / "building_canny_gen.png"
DEPTH_GEN_PATH = OUTPUT_DIR / "building_depth_proxy_gen.png"
COLOR_GEN_PATH = OUTPUT_DIR / "building_render_gen.png"
GEN_WIDTH, GEN_HEIGHT = 832, 1248

GEN_SIZE = 1024  # 旧・SDXL標準正方形解像度（過去の生成物との比較用に残す）


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
    return edges  # 0/255 の単チャンネル


def make_depth_proxy(alpha: np.ndarray) -> np.ndarray:
    """シルエット(alpha)から distance transform ベースの疑似depthを作る。
    白=近い(建物の中心付近)、黒=遠い(背景・輪郭)。
    """
    mask = (alpha > 10).astype(np.uint8) * 255
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    if dist.max() > 0:
        dist_norm = (dist / dist.max() * 255).astype(np.uint8)
    else:
        dist_norm = dist.astype(np.uint8)
    # 背景は最遠(黒=0)のまま、建物内部だけ distance transform の階調を使う
    depth = np.where(mask > 0, dist_norm, 0).astype(np.uint8)
    return depth


def to_pil_gray(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr).convert("L")


def resize_to(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return img.resize(size, Image.NEAREST)


def main() -> None:
    rgba = load_rgba(SRC_PATH)
    alpha = rgba[:, :, 3]
    w, h = rgba.shape[1], rgba.shape[0]
    print(f"[main] input: {SRC_PATH.name} ({w}x{h})")

    rgb_on_white = composite_on_white(rgba)
    Image.fromarray(rgb_on_white).save(OUTPUT_DIR / "building_render_on_white.png")

    canny = make_canny(rgb_on_white)
    canny_img = to_pil_gray(canny)
    canny_img.save(CANNY_PATH)
    resize_to(canny_img, (GEN_WIDTH, GEN_HEIGHT)).save(CANNY_GEN_PATH)
    print(f"[canny] saved: {CANNY_PATH}, {CANNY_GEN_PATH} ({GEN_WIDTH}x{GEN_HEIGHT})")

    depth = make_depth_proxy(alpha)
    depth_img = to_pil_gray(depth)
    depth_img.save(DEPTH_PATH)
    resize_to(depth_img, (GEN_WIDTH, GEN_HEIGHT)).save(DEPTH_GEN_PATH)
    print(f"[depth_proxy] saved: {DEPTH_PATH}, {DEPTH_GEN_PATH} ({GEN_WIDTH}x{GEN_HEIGHT})")

    # ControlNet生成結果との見比べ用に、元カラー画像も生成解像度へリサイズして保存
    resize_to(Image.fromarray(rgb_on_white), (GEN_WIDTH, GEN_HEIGHT)).save(COLOR_GEN_PATH)
    print(f"[color_gen] saved: {COLOR_GEN_PATH}")


if __name__ == "__main__":
    main()
