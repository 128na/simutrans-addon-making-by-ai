"""
シルエットIoU簡易計測スクリプト。

現行Blenderレンダー(側面図、RGBA透過)とt2i目標画像(グレー背景の単一車両写真)の車両
シルエットを簡易的に二値マスク化し、外接矩形基準でラフに位置合わせしたうえで
IoU(Intersection over Union)を計算する。

方針（深追いしない）:
- render側: alphaチャンネルを閾値二値化するだけ（transparent PNGなので厳密に前景/背景が分かる）
- target側: rembg等の学習済み背景除去モデルは導入せず、背景色（四隅から推定）との色距離を
  Otsu二値化し、最大連結成分だけを残す軽量な方法で代替する
- アライメント: ICP等の厳密な位置合わせは行わず、各マスクの外接矩形で切り出して
  同じ正方形キャンバスへリサイズする（アスペクト比は保持しない）ラフな正規化のみ
- 数値は「近づき方の傾向を掴むための参考値」であり、厳密なピクセル対応・形状一致度の
  正確な測定ではない点に注意（README参照）

Usage:
    python compute_silhouette_iou.py <render_png> [--target <target_png>] [--label round0]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TARGET = SCRIPT_DIR / "output" / "target_side_reference.png"
CANVAS_SIZE = 512  # 位置合わせ後の共通キャンバスサイズ


def render_mask_from_rgba(path: Path, alpha_thresh: int = 10) -> np.ndarray:
    """透過PNGのalphaチャンネルを閾値二値化してシルエットマスクを作る。"""
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    mask = (alpha > alpha_thresh).astype(np.uint8) * 255
    return mask


def target_mask_from_photo(path: Path) -> np.ndarray:
    """グレー背景の単一車両写真から、背景色との色距離+Otsu二値化+最大連結成分抽出で
    車両シルエットマスクを作る簡易手法（rembg等の学習済みモデルは使わない）。
    """
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]

    # 背景色を四隅の平均から推定(コーナーはほぼ確実に背景)
    corner_size = max(4, min(h, w) // 20)
    corners = np.concatenate([
        arr[:corner_size, :corner_size].reshape(-1, 3),
        arr[:corner_size, -corner_size:].reshape(-1, 3),
        arr[-corner_size:, :corner_size].reshape(-1, 3),
        arr[-corner_size:, -corner_size:].reshape(-1, 3),
    ], axis=0)
    bg_color = corners.mean(axis=0)

    # 背景色からの色距離(ユークリッド距離)
    dist = np.linalg.norm(arr - bg_color, axis=2)
    dist_u8 = np.clip(dist, 0, 255).astype(np.uint8)

    # Otsuで色距離を二値化(前景/背景の閾値を自動決定)
    _, binary = cv2.threshold(dist_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 最大連結成分のみ残す(影・ノイズの小片を除去)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels <= 1:
        return binary  # 前景が見つからない場合はそのまま返す
    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == largest_label).astype(np.uint8) * 255
    return mask


def bbox_of(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        raise ValueError("マスクが空です(前景ピクセルが見つかりません)")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def normalize_to_bbox(mask: np.ndarray, size: int = CANVAS_SIZE) -> np.ndarray:
    """外接矩形で切り出し、正方形キャンバスへ引き伸ばす簡易アライメント。
    位置・スケールの厳密な整合(ICP等)は行わず、あくまで「車両の外接矩形を正規化して
    重ねる」というラフな手法にとどめる。アスペクト比も保持しない。
    """
    x0, y0, x1, y1 = bbox_of(mask)
    cropped = mask[y0:y1, x0:x1]
    resized = cv2.resize(cropped, (size, size), interpolation=cv2.INTER_NEAREST)
    return resized


def compute_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    a = mask_a > 0
    b = mask_b > 0
    intersection = int(np.logical_and(a, b).sum())
    union = int(np.logical_or(a, b).sum())
    if union == 0:
        return 0.0
    return intersection / union


def save_overlay(mask_a: np.ndarray, mask_b: np.ndarray, out_path: Path) -> None:
    """render=赤, target=青, 重なり=紫 のデバッグ用オーバーレイ画像を保存する。"""
    h, w = mask_a.shape
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    a = mask_a > 0
    b = mask_b > 0
    overlay[..., 0] = np.where(a, 255, 0)  # R: render
    overlay[..., 2] = np.where(b, 255, 0)  # B: target
    overlay[np.logical_and(a, b)] = (200, 0, 200)  # 重なり=紫
    Image.fromarray(overlay).save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="簡易シルエットIoU計測（傾向把握用、厳密指標ではない）")
    parser.add_argument("render_png", type=Path, help="Blenderレンダー(RGBA透過PNG)のパス")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="t2i目標画像のパス")
    parser.add_argument("--label", default="round", help="出力ファイル名に使うラベル")
    parser.add_argument("--outdir", type=Path, default=SCRIPT_DIR / "output" / "iou_debug")
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    render_mask_raw = render_mask_from_rgba(args.render_png)
    target_mask_raw = target_mask_from_photo(args.target)

    render_mask = normalize_to_bbox(render_mask_raw)
    target_mask = normalize_to_bbox(target_mask_raw)

    iou = compute_iou(render_mask, target_mask)

    Image.fromarray(render_mask).save(args.outdir / f"{args.label}_render_mask.png")
    Image.fromarray(target_mask).save(args.outdir / f"{args.label}_target_mask.png")
    save_overlay(render_mask, target_mask, args.outdir / f"{args.label}_overlay.png")

    print(f"[compute_silhouette_iou] label={args.label}")
    print(f"[compute_silhouette_iou] render={args.render_png.name} target={args.target.name}")
    print(f"[compute_silhouette_iou] IoU = {iou:.4f} ({iou * 100:.1f}%)")


if __name__ == "__main__":
    main()
