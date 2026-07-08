"""
生成画像から背景色と「その暗いバリエーション(=落ち影)」をまとめて透過化する後処理。

前提: SDXLの生成結果は背景がほぼ均一なフラットカラーで、影はその背景色の
明度(Value)だけを落とした同系色ブロブとして現れる（今回観察された全パターンで共通）。
そのため HSV空間で Hue・Saturation が背景に近い画素は「背景 or 影」とみなして
透過化し、Value(明るさ)の違いは無視する。建物本体の壁・屋根はHue/Saturationが
背景と明確に異なる（木材の黄褐色、レンガの赤、石材のベージュ等）ため、この基準で
背景・影と区別できるという狙い。

プロンプト側でのnegative/positive指定だけでは影を安定して抑制できなかった
（3パターン中1パターンで強い落ち影が残存）ため、フォールバックとして追加した。

Usage:
    python postprocess_remove_shadow.py <input.png> [output.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# HSV空間でのしきい値（OpenCV流儀: H:0-179, S/V:0-255）
HUE_TOLERANCE = 10       # 背景Hueからの許容差
SAT_TOLERANCE = 28       # 背景Saturationからの許容差（影は彩度もやや落ちるため広めに許容）
CORNER_MARGIN = 4        # 背景色サンプリングに使う四隅の余白幅
MORPH_KERNEL = 5         # マスクのノイズ除去用モルフォロジーカーネルサイズ


def sample_background_hsv(hsv: np.ndarray, margin: int = CORNER_MARGIN) -> np.ndarray:
    """画像四隅から背景色(HSV)をサンプリングして中央値を返す。"""
    h, w = hsv.shape[:2]
    corners = np.concatenate(
        [
            hsv[0:margin, 0:margin].reshape(-1, 3),
            hsv[0:margin, w - margin : w].reshape(-1, 3),
            hsv[h - margin : h, 0:margin].reshape(-1, 3),
            hsv[h - margin : h, w - margin : w].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(corners, axis=0)


def hue_distance(h1: np.ndarray, h2: float) -> np.ndarray:
    """OpenCV Hueは0-179で循環するため、循環距離を計算する。"""
    d = np.abs(h1.astype(np.int16) - int(round(h2)))
    return np.minimum(d, 180 - d)


def remove_shadow(src_path: Path, dst_path: Path) -> dict:
    bgr = cv2.imread(str(src_path), cv2.IMREAD_COLOR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    bg_h, bg_s, _bg_v = sample_background_hsv(hsv)

    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]

    dh = hue_distance(h_ch, bg_h)
    ds = np.abs(s_ch.astype(np.int16) - int(round(bg_s)))

    is_bg_or_shadow = (dh <= HUE_TOLERANCE) & (ds <= SAT_TOLERANCE)

    mask_opaque = (~is_bg_or_shadow).astype(np.uint8) * 255

    # ノイズ除去: 小さな穴埋め(close)→孤立ノイズ除去(open)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL, MORPH_KERNEL))
    mask_opaque = cv2.morphologyEx(mask_opaque, cv2.MORPH_CLOSE, kernel)
    mask_opaque = cv2.morphologyEx(mask_opaque, cv2.MORPH_OPEN, kernel)

    # 最大連結成分のみ残す（建物本体以外の孤立した誤検出ノイズを除去）
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_opaque, connectivity=8)
    if n_labels > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask_opaque = np.where(labels == largest, 255, 0).astype(np.uint8)

    # 境界をわずかにぼかしてアンチエイリアス感を出す
    mask_soft = cv2.GaussianBlur(mask_opaque, (3, 3), 0)

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgba = np.dstack([rgb, mask_soft])
    Image.fromarray(rgba, mode="RGBA").save(dst_path)

    total = mask_opaque.size
    removed = int((mask_opaque == 0).sum())
    return {
        "bg_hue": float(bg_h),
        "bg_sat": float(bg_s),
        "removed_ratio": removed / total,
    }


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python postprocess_remove_shadow.py <input.png> [output.png]")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_noshadow_post.png")
    stats = remove_shadow(src, dst)
    print(f"[remove_shadow] {src.name} -> {dst.name}")
    print(f"  background HSV(H,S) ~= ({stats['bg_hue']:.1f}, {stats['bg_sat']:.1f})")
    print(f"  removed(transparent) ratio = {stats['removed_ratio'] * 100:.1f}%")


if __name__ == "__main__":
    main()
