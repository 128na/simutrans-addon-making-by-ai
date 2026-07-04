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

### dat_linter（.dat の静的検証・整形・連結解析）
`refs/simutrans-dat-linter` のreleaseビルドにPATHが通っており、フルパス指定不要で
どこからでも呼び出せる。
```
dat_linter lint <path|dir|glob>      # 静的検証（複数ファイル一括対応）
dat_linter fmt <path|dir|glob> [-w]  # 正規化・並び替え（デフォルトreorder、--no-reorderで無効化）
dat_linter analyze <dir> --kind coupling  # obj=vehicle の連結制約解析
dat_linter list [--source lint|fmt|analyze]  # include/exclude設定可能なルールcode一覧
```
ルールのinclude/exclude・出力言語(en/ja)は初回実行時に自動生成される
`dat_linter.toml` で設定する。詳細は`refs/simutrans-dat-linter/README.md`参照。

## try-out 作業手順

### 新しい実験を始めるとき

1. `try-out/<実験名>/` ディレクトリを作成
2. Blender スクリプト・dat・PNG など成果物をそのディレクトリに置く
3. 実験が完了したら `try-out/<実験名>/README.md` を作成
   （GitHub上でディレクトリを開いた時に自動表示されるよう `memo.md` でなく `README.md` とする）

### README.md フォーマット

```markdown
# <実験タイトル>

作業日: YYYY-MM-DD（複数日にまたがる場合は YYYY-MM-DD〜YYYY-MM-DD）

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
try-out/          実験ディレクトリ（各実験に README.md）
  blender/        Blenderレンダリング PoC
  station_test/   pak128 駅拡張建物フルパイプライン検証
knowledge.md      技術知見（カメラ仕様・dat制約・Blenderノート）
roadmap.md        目標・フェーズ・TODO
```

`simutrans-dat-parser`（TypeScript）/`simutrans-image-merger`（Python）/
`simutrans-image-util`（TypeScript）/`simutrans-dat-linter`（Rust製 dat linter。
try-out/dat_linter を独立化）は、パイプライン構成ツールとして開発しているが
このリポジトリのコードから直接呼び出す予定は無いため、submodule管理はせず
`refs/simutrans-dat-parser`等（`refs/`配下、.gitignore対象）として参照するだけに
している。同様に `refs/simutrans`（makeobj本体のC++ソース、動作仕様の参照専用）・
`refs/pak128`（pak128公式データ、lint/fmtの実データ検証専用）・`simuwin/`
（ゲーム本体）・`refs/`配下の参照アドオンも読み取り専用の参照データとして
`refs/` に置いている。現時点でこのリポジトリ自体はsubmoduleを持たない。

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
cursor=icon.0.0
icon=icon.0.0
BackImage[0][0][0][0][0]=image.0.0
BackImage[1][0][0][0][0]=image.0.0
BackImage[2][0][0][0][0]=image.0.0
BackImage[3][0][0][0][0]=image.0.0
```

- `cursor` / `icon` がないとビルドメニューに表示されない
- アイコン画像は 128×128、背景不透過（左上(0,0)が透明だとゲームが認識しない）
- `makeobj pak128` は全画像が **128の倍数** サイズでないとエラー
- makeobj はパラメーター不足でもエラーを出さない（エラーなし ≠ 正しい）
- 画像参照は `ファイル名.行.列`（`.png` を含めない）。makeobj は最初の `.` より前だけをファイル名として扱い `.png` を自動付与するため、row/col が0でない場合に literal に `.png` を挟むと行/列を誤読する（詳細は [knowledge.md](knowledge.md) 参照）
