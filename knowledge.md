# Knowledge

## Simutrans イソメトリック仕様
参考: https://ahozura.kasu.me/portal/?p=666 （Metasequoiaでの制作手順）

- カメラ種類: 直交投影 (Orthographic)
- 仰角 (pitch): **30°** → Blender X rotation = 60°
- 方位角 (head): 45°（SE視点）、他方向は 135°/225°/315°
- 高さスケール: **X:Y:Z = 100:81.6:100**（height = side × √6/3 ≈ 0.816）
- タイルサイズ: pak128 = 128×64px / タイル（2:1比率）
- 側面が暗い場合: 自己発光 0.2〜0.3 を設定する

## Blender ヘッドレスレンダリング

**実行コマンド**
```
blender --background --python script.py
```

**Blender 5.1.x 固有の注意**
- render engine: `'BLENDER_EEVEE'`（`BLENDER_EEVEE_NEXT` は 4.x 系の名称）
- `use_nodes` は Blender 6.0 で削除予定だが 5.x では動作する

**カメラ設定パターン**
```python
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2)  # 1×1 BUタイルを128pxにぴったり収める
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

# カメラ位置はrotationから逆算（手動で設定するとフレームがズレる）
bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, z_center))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * distance
```

**ortho_scale と解像度の関係**
- 1タイル = 1×1 BU とする
- `ortho_scale = tile_side × √2` で Nタイル幅なら `N × √2`
- 1 BU ≈ 90.5px（非整数だが公式はシンプル）

**透過PNG出力**
```python
scene.render.film_transparent = True
scene.render.image_settings.color_mode = 'RGBA'
```

## makeobj / dat 仕様

**画像制約**
- `makeobj pak128` は全画像の縦横サイズが **128の倍数** でないとエラー
- アイコン画像も 128×128 必須（48×48 等は不可）
- アイコン画像の左上(0,0)ピクセルが透過だとゲームが認識しない → 背景は不透過で塗りつぶす

**building dat の最小構成（駅拡張建物）**
```dat
obj=building
type=extension
waytype=track
enables_pax=1
NoInfo=1
Dims=1,1,4
cursor=icon.png.0.0
icon=icon.png.0.0
BackImage[0][0][0][0][0]=image.png.0.0
```

**building type 一覧（makeobj 60.11）**
| type | 説明 | 備考 |
|------|------|------|
| `extension` + `waytype=track` | 鉄道駅拡張建物 | ✓ ゲーム内表示確認済み |
| `stop` + `waytype=track` | 鉄道駅本体 | |
| `cur` | 観光地建物 | type指定のみでは表示されなかった（要調査） |
| `res`/`com`/`ind` | 市街地建物 | 自動生成 |
| `station`, `extension_building=1` | **obsolete** | 現 makeobj でビルドエラー |

**BackImage インデックス形式**
- 5形式 `[l][y][x][h][phase]` と 6形式 `[l][y][x][h][phase][season]` どちらも有効
- `seasons==1` の場合のみ 6→5 フォールバックあり
- image参照 `.x.y` は 128px グリッドのコラム/行インデックス（`.png` 拡張子あり・なし両方可）

**デバッグ**
- `makeobj VERBOSE DEBUG` で画像の読み込み詳細（座標・サイズ・オフセット）を確認できる
- makeobj はパラメーター不足・矛盾をほぼ無視して pak 生成する（エラーなし ≠ 正しい）

## 自作ツール（サブモジュール）
| リポジトリ | 言語 | 役割 |
|---|---|---|
| simutrans-dat-parser | TypeScript | .dat 解析・書き込み |
| simutrans-image-util | TypeScript | 画像合成・透過・タイル分割 |
| simutrans-image-merger | Python | 画像レイヤー合成バッチ |
| simutrans（本体） | C++ | makeobj（dat+画像→pak） |
