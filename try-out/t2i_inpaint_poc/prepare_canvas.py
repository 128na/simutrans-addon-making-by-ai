"""建物PNG(128x128 RGBA)から、inpaint用のキャンバス画像・マスク画像・ControlNet用シルエット画像を作る。

観点2 PoC: PLATEAU建物レンダリング(building.png)を、生成対象(inpaint対象)を
「crop.pngが示す菱形の地面領域のうち建物が占めていない部分」に限定して周辺装飾する。

## フィードバック対応(2026-07-08): crop.pngによる菱形領域限定

v1(output/v1_freeform_full_canvas/)では「建物以外の256x256キャンバス全域」を生成対象にしていたが、
ユーザーレビューにより「ゲーム内で実際に地面として描画されるのはpak128の2:1菱形部分のみで、
正方形画像の四隅(および追加していた256x256キャンバスの外側マージン)は本来何も表示されない領域」
との指摘を受けた。四隅・マージンまで生成対象にしていたことが、v1の「周辺の植栽・地面ブロックが
平面図的に浮いて見える」破綻の一因になっていた可能性がある。

対応として、`crop.png`(128x128 RGBA。building.pngと同じ座標系。透明=菱形の地面候補、
青(0,0,255)=四隅の除外領域)を導入し、
    生成マスク = crop.pngの透明領域(菱形) ∩ 建物のアルファでない部分(建物は引き続き保護)
に変更した。

### 【つまずき】v2(菱形マスク+旧マージンキャンバス)は生成対象が「ほぼ真っ平らな灰色」になった

菱形マスクをそのまま旧v1の256(参考)/1024(生成)キャンバス(建物の周囲に外側マージンを
追加していた設計)に適用したところ(output/v2_diamond_with_margin/)、生成領域(菱形-建物)は
1024x1024キャンバスの約6%程度しかなく、残り94%(外側マージン+四隅)が単色グレーの
「保護領域(inpaint対象外)」として常時見えている状態になった。この結果、SDXL inpaintingモデルは
「周囲がほぼ全面グレーの単色コンテキスト」を強く手がかりにして、菱形の生成対象領域も
同じグレーのまま(建物以外はほぼ無地・無変化)を出力し続けた（3シードとも同じ結果）。
つまり「生成対象を厳密に絞ったことで、逆に周辺コンテキストのグレー比率が支配的になりすぎ、
モデルが装飾を生成する動機を失った」という新たな失敗パターンが判明した。

### 対応: 外側マージンを廃止し、キャンバスをタイル自体の拡大に一本化(このv3設計)

上記の反省を踏まえ、v1で導入していた「建物の周囲に余白を追加する256/1024キャンバス」という
考え方自体をやめ、**crop.png/building.pngの128x128タイル自体をそのまま拡大しただけ**のキャンバスに
変更した(外側マージンなし、offset=0)。これにより「グレーの保護領域」は四隅(タイル内の約75%)のみとなり、
v2よりコンテキスト中のグレー比率を下げた。

出力:
  canvas_gen.png / mask_gen.png / silhouette_gen.png : 1024x1024(タイルをそのまま8倍拡大、マージンなし)。
                SDXLは1024x1024ネイティブ学習のため、256x256でそのまま生成すると
                (32x32 latentしかなく)崩壊した画像になることが実機検証で判明した(v1時点)。
  canvas.png  : 256x256 RGB(参考/最終合成用。タイルを2倍拡大、マージンなし)。
  mask.png    : 256x256 グレースケール(参考用)。白=inpaint対象(菱形∩建物以外)、黒=保護(建物+四隅)。
  silhouette.png : 256x256 RGB(参考用)。ControlNet(canny)入力用の建物シルエット。

使い方:
    python prepare_canvas.py
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
FINAL_SCALE = 2   # 参考/最終合成用キャンバスの拡大率(マージンなし、単純拡大)
GEN_SCALE = 8     # SDXLネイティブ解像度(1024)に合わせるための拡大率(マージンなし、単純拡大)

CANVAS_SIZE = TILE_SIZE * FINAL_SCALE      # 256
GEN_CANVAS_SIZE = TILE_SIZE * GEN_SCALE    # 1024

BACKGROUND_GRAY = (127, 127, 127)
MASK_DILATE_PX_BASE = 3  # 128x128タイル基準の侵食量。各解像度でスケールして使う
ALPHA_THRESHOLD = 10  # これ以上のアルファ値を「建物が存在するピクセル」とみなす


def _compose(
    building: Image.Image, crop: Image.Image, size: int, dilate_px: int
) -> tuple[Image.Image, Image.Image, Image.Image]:
    """タイル(building.png/crop.png)をsize x sizeへ単純拡大し、キャンバス・マスク・シルエットを作る。

    外側マージンは追加しない(offset=0)。マージンを追加するとinpaint対象外(グレー)の
    コンテキストが支配的になり生成が停滞する問題がv2で判明したため、v3ではタイル自体の
    拡大のみで構成する。
    """
    building_resized = building.resize((size, size), Image.LANCZOS)
    # crop.pngは菱形の直線境界を持つ二値マスクなのでNEARESTでリサイズし、境界をぼかさない
    crop_resized = crop.resize((size, size), Image.NEAREST)

    # --- canvas: 中間グレー背景 + 建物をアルファ合成(offset=0でタイル全面に敷き詰め) ---
    canvas_rgba = Image.new("RGBA", (size, size), (*BACKGROUND_GRAY, 255))
    canvas_rgba.alpha_composite(building_resized, dest=(0, 0))
    canvas = canvas_rgba.convert("RGB")

    # --- 建物の保護領域(建物アルファをしきい値化 → 保護領域を侵食) ---
    alpha = building_resized.split()[-1]
    building_binary = alpha.point(lambda a: 255 if a >= ALPHA_THRESHOLD else 0)  # 建物=255, 背景=0

    if dilate_px > 0:
        k = dilate_px * 2 + 1  # MinFilterのカーネルサイズは奇数
        protect_eroded = building_binary.filter(ImageFilter.MinFilter(k))
    else:
        protect_eroded = building_binary

    # --- 菱形の生成候補領域(crop.pngの透明部分) ---
    crop_alpha = crop_resized.split()[-1]
    diamond_binary = crop_alpha.point(lambda a: 255 if a == 0 else 0)  # 透明(菱形)=255, 青(四隅)=0

    # --- 最終マスク: 菱形 かつ 建物保護でない部分だけを生成対象(白)にする ---
    diamond_np = np.array(diamond_binary) > 0
    protect_np = np.array(protect_eroded) > 0
    generate_np = diamond_np & ~protect_np
    mask = Image.fromarray((generate_np * 255).astype(np.uint8), mode="L")

    # --- silhouette: ControlNet(canny)入力用。建物シルエット=白、背景=黒の二値画像 ---
    silhouette = Image.merge("RGB", (building_binary, building_binary, building_binary))

    return canvas, mask, silhouette


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    building = Image.open(INPUT_BUILDING).convert("RGBA")
    assert building.size == (TILE_SIZE, TILE_SIZE), f"unexpected size: {building.size}"
    crop = Image.open(INPUT_CROP).convert("RGBA")
    assert crop.size == (TILE_SIZE, TILE_SIZE), f"unexpected crop.png size: {crop.size}"

    # 参考/最終合成用(256x256、タイルを2倍拡大)
    dilate_final = round(MASK_DILATE_PX_BASE * FINAL_SCALE)
    canvas, mask, silhouette = _compose(building, crop, CANVAS_SIZE, dilate_final)
    canvas.save(OUTPUT_DIR / "canvas.png")
    mask.save(OUTPUT_DIR / "mask.png")
    silhouette.save(OUTPUT_DIR / "silhouette.png")

    # SDXL生成用(1024x1024、タイルを8倍拡大)
    dilate_gen = round(MASK_DILATE_PX_BASE * GEN_SCALE)
    canvas_gen, mask_gen, silhouette_gen = _compose(building, crop, GEN_CANVAS_SIZE, dilate_gen)
    canvas_gen.save(OUTPUT_DIR / "canvas_gen.png")
    mask_gen.save(OUTPUT_DIR / "mask_gen.png")
    silhouette_gen.save(OUTPUT_DIR / "silhouette_gen.png")

    for name, img in [
        ("canvas.png", canvas), ("mask.png", mask), ("silhouette.png", silhouette),
        ("canvas_gen.png", canvas_gen), ("mask_gen.png", mask_gen), ("silhouette_gen.png", silhouette_gen),
    ]:
        print(f"[prepare_canvas] saved: {OUTPUT_DIR / name} {img.size} {img.mode}")


if __name__ == "__main__":
    main()
