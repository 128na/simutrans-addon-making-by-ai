# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIエージェント主体で Simutrans アドオン（pakセット）を生成するパイプラインの研究・開発リポジトリ。
詳細な目標・ロードマップは [roadmap.md](roadmap.md)、技術的な知見は [knowledge.md](knowledge.md) を参照。

## 確認済みパイプライン

```
テキスト/スクリプト
→ Blender ヘッドレスレンダリング（約2秒）→ PNG（128×128 RGBA）
→ .dat 作成 → makeobj pak128 → .pak → Simutrans ゲーム内表示
```

## コマンド

### Blender ヘッドレスレンダリング
```
blender --background --python script.py
```

デバッグ出力確認:
```
blender --background --python script.py 2>&1
```

### makeobj pak化
```
# カレントディレクトリに .dat と PNG が存在する状態で実行
makeobj pak128 output.pak input.dat

# 詳細ログ付き（画像の座標・サイズ・オフセットを出力）
makeobj VERBOSE DEBUG pak128 output.pak input.dat
```

### Simutrans でアドオンを読み込む
生成した `.pak` を Simutrans の `pak128/addons/` に置いて起動する。

## try-out 作業手順

### 新しい実験を始めるとき

1. `try-out/<実験名>/` ディレクトリを作成
2. Blender スクリプト・dat・PNG など成果物をそのディレクトリに置く
3. 実験が完了したら `try-out/<実験名>/memo.md` を作成

### memo.md フォーマット

```markdown
# <実験タイトル>

## 目標
<何を確認したかったか>

## 結果
達成 / 未達成 / 継続中

## 試したこと
- <試みた手順や設定変更>

## 得られた知見や失敗
- <次回に活かせる発見・エラーの原因>
```

## リポジトリ構成

```
try-out/          実験ディレクトリ（各実験に memo.md）
  blender/        Blenderレンダリング PoC
  station_test/   pak128 駅拡張建物フルパイプライン検証
knowledge.md      技術知見（カメラ仕様・dat制約・Blenderノート）
roadmap.md        目標・フェーズ・TODO
simutrans/        submodule: 本体C++ソース + makeobj
simutrans-dat-parser/      submodule: TypeScript
simutrans-image-merger/    submodule: Python
simutrans-image-util/      submodule: TypeScript
```

`simuwin/`（ゲーム本体）と `refs/`（参照アドオン）は .gitignore により除外。

## Blender スクリプト パターン

```python
import math, mathutils, bpy

# カメラ（必ずrotation設定後にlocationを逆算）
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2)  # 1×1 BU タイル → 128px ぴったり
cam.rotation_euler = (math.radians(60), 0, math.radians(45))
bpy.context.view_layer.update()
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * distance

# レンダー設定
scene.render.engine = 'BLENDER_EEVEE'         # Blender 5.1
scene.render.film_transparent = True
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = 128
scene.render.resolution_y = 128
```

キューブの高さスケール: `cube.scale = (1.0, 1.0, 0.816)` （√6/3 ≈ 0.816）

## dat 最小構成例（駅拡張建物）

```dat
obj=building
name=my_addon
type=extension
waytype=track
enables_pax=1
NoInfo=1
Dims=1,1,4
cursor=icon.png.0.0
icon=icon.png.0.0
BackImage[0][0][0][0][0]=image.png.0.0
BackImage[1][0][0][0][0]=image.png.0.0
BackImage[2][0][0][0][0]=image.png.0.0
BackImage[3][0][0][0][0]=image.png.0.0
```

- `cursor` / `icon` がないとビルドメニューに表示されない
- アイコン画像は 128×128、背景不透過（左上(0,0)が透明だとゲームが認識しない）
- `makeobj pak128` は全画像が **128の倍数** サイズでないとエラー
- makeobj はパラメーター不足でもエラーを出さない（エラーなし ≠ 正しい）
