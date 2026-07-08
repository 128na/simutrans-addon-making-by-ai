"""入口(entrance)位置の推定ロジック。

v5(段階的denoiseマスク・ControlNetガイド線)で共通利用する。building.png(不透明=建物シルエット)と
crop.png(透明=菱形地面候補)から、「生成対象の三日月が開けている菱形頂点(既定=bottom頂点。
isometric視点でカメラに最も近い南側で、v4/v5のBBOXが対象とする範囲でもある)に最も近い、
建物シルエットの境界点」を entrance point として近似的に決定する。正確なドア座標のメタデータは
存在しないため、この近似を「入口」とみなす(タスク指示: "生成対象の三日月に最も近い建物の辺、を
入口とみなす近似でよい")。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

TILE_SIZE = 128


def load_masks(building_path: Path, crop_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """building_alpha(bool, 不透明=True)とdiamond(bool, 菱形地面候補=True)を返す。"""
    building = Image.open(building_path).convert("RGBA")
    crop = Image.open(crop_path).convert("RGBA")
    assert building.size == (TILE_SIZE, TILE_SIZE)
    assert crop.size == (TILE_SIZE, TILE_SIZE)
    building_alpha = np.array(building.split()[-1]) >= 10
    crop_alpha = np.array(crop.split()[-1])
    diamond = crop_alpha == 0
    return building_alpha, diamond


def diamond_vertices(diamond: np.ndarray) -> dict[str, tuple[int, int]]:
    """菱形の4頂点(top/bottom/left/right)を(x,y)で返す。"""
    ys, xs = np.where(diamond)
    return {
        "top": (int(xs[ys.argmin()]), int(ys.min())),
        "bottom": (int(xs[ys.argmax()]), int(ys.max())),
        "left": (int(xs.min()), int(ys[xs.argmin()])),
        "right": (int(xs.max()), int(ys[xs.argmax()])),
    }


def exit_point(diamond: np.ndarray, exit_vertex_name: str = "bottom") -> tuple[int, int]:
    """通路が向かう先(タイル境界の頂点)。既定はbottom(南、カメラ手前側)。"""
    return diamond_vertices(diamond)[exit_vertex_name]


def find_entrance_point(
    building_alpha: np.ndarray, diamond: np.ndarray, exit_vertex_name: str = "bottom"
) -> tuple[int, int]:
    """建物シルエットの境界のうち、exit_vertexに最も近い点を「入口」として返す(128タイル座標系)。

    各x列について、その列で建物が存在する最下端(=crescent側に接する境界)を候補点とし、
    そのうち exit_vertex からのユークリッド距離が最小の点を選ぶ。
    """
    ex, ey = diamond_vertices(diamond)[exit_vertex_name]
    candidates: list[tuple[int, int]] = []
    for x in range(TILE_SIZE):
        col = building_alpha[:, x]
        ys_col = np.where(col)[0]
        if len(ys_col) == 0:
            continue
        by = int(ys_col.max())
        if by + 1 < TILE_SIZE and diamond[by + 1, x] and not building_alpha[by + 1, x]:
            candidates.append((x, by))
    if not candidates:
        raise RuntimeError("entrance候補が見つからない(建物がcrescentに接していない可能性)")
    best = min(candidates, key=lambda p: (p[0] - ex) ** 2 + (p[1] - ey) ** 2)
    return best
