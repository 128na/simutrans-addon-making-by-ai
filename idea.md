# AIエージェント主体でSimutransのアドオン作成するプロジェクト

## 最終目標
pakセット作成（全タイプのアドオンが作成できる状態）

## 現在のブロッカー
- 画像生成をどうするか（現状：ペイントソフトでレイヤ管理）
- アドオン形式によるバリエーションが多い（車両・建物・軌道で生成すべき画像パターンが大きく異なる）

## 戦略
シンプルな1枚絵で済むものから手順確立 → 徐々に対応形式を拡大

### アドオンタイプ別画像複雑度
| タイプ | 画像枚数 | 備考 |
|--------|---------|------|
| groundobj（地面装飾） | 1枚 | **最初のターゲット** |
| attraction_land | 1〜4枚 | 回転方向 |
| city building | 4枚 | 方向別 |
| vehicle（車両） | 8方向 × 状態数 | 複雑 |
| way（軌道） | 直線・カーブ・分岐... | 複雑 |

## 画像生成パイプライン（採用方針）

**テキスト → Blender Python スクリプト → ヘッドレスレンダリング → PNG**

### なぜ2D直接生成でなくBlender経由か
- 2D生成AIはイソメトリック角度の再現が不安定
- Blender経由なら角度を数学的に固定できる（arctan(0.5) = 26.57°）
- 同じ3Dモデルから8方向を一括生成できる（車両対応時に有効）

### Simutrans イソメトリック仕様
参考: https://ahozura.kasu.me/portal/?p=666 （Metasequoiaでの制作手順）

- カメラ種類: 直交投影 (Orthographic)
- 仰角 (pitch): **30°** → Blender X rotation = 60°  ※当初 26.57° と推定していたが誤り
- 方位角 (head): 45°（SE方向がメイン視点）、他方向は -135°/-45°/135°
- 高さスケール: **X:Y:Z = 100:81.6:100**（height = side × √6/3 ≈ 0.816）
- タイルサイズ: pak128 = 128×64px / タイル（2:1比率）
- 側面が暗い場合: 自己発光 0.2〜0.3 を設定する

## 参照ツール（自作）
| リポジトリ | 言語 | 役割 |
|---|---|---|
| simutrans-dat-parser | TypeScript | .dat 解析・書き込み |
| simutrans-image-util | TypeScript | 画像合成・透過・タイル分割 |
| simutrans-image-merger | Python | 画像レイヤー合成バッチ |
| simutrans（本体） | C++ | makeobj（dat+画像→pak） |

## try-out の記録

### blender/ - Blenderヘッドレスレンダリング検証
- `isometric_box.py`: イソメトリックボックスのレンダリング PoC
- `output/isometric_box.png`: 生成物

**確認済み事項:**
- Blender 5.1.2 ヘッドレス動作 ✓（約2秒）
- 透過PNG（RGBA）出力 ✓
- render engine は `'BLENDER_EEVEE'`（`BLENDER_EEVEE_NEXT` は 4.x 系の名称で 5.x では無効）
- `use_nodes` は Blender 6.0 で削除予定だが 5.x では動作する
- カメラ位置は rotation から逆算して設定しないとフレームがズレる
  ```python
  bpy.context.view_layer.update()
  forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
  cam.location = target - forward * distance
  ```
- 仰角 30°・高さスケール 0.816・自己発光 0.25 でプロポーション良好な結果を確認

### dat / makeobj 仕様メモ
- `cursor` と `icon` フィールドがないとゲームのビルドメニューに表示されない
- `makeobj pak128` は **全画像の縦横サイズが 128 の倍数**でないとエラー
  - アイコン画像も 128×128 必須（48×48 等は不可）
- **アイコン画像の左上(0,0)が透過だと認識されない** → 背景は不透過で塗りつぶすこと
- building の `type` 値（現 makeobj 60.11 での正式名）:
  - `extension` + `waytype=track` = 鉄道駅拡張建物 ✓（ゲーム内表示確認済み）
  - `stop` + `waytype=track` = 鉄道駅本体
  - `cur` = 観光地建物（type指定だけでは表示されなかった）
  - `res`/`com`/`ind` = 市街地建物（自動生成）
  - `type=station`, `extension_building=1` は**obsolete**（現 makeobj でビルドエラー）
- 駅拡張建物の表示に必要な最小フィールド:
  ```
  type=extension, waytype=track, enables_pax=1, NoInfo=1
  Dims=1,1,4 （4方向レイアウト）
  cursor=xxx.png.0.0, icon=xxx.png.0.0
  ```
- dat の BackImage インデックス: 5形式 `[l][y][x][h][phase]` と 6形式 `[l][y][x][h][phase][season]` どちらも有効
  - `seasons==1` の場合のみ 6→5 フォールバックあり
- image 参照の `.x.y` は 128px グリッドのコラム/行インデックス（`.png` 拡張子あり・なし両方可）
- `makeobj VERBOSE DEBUG` で画像読み込み詳細（座標・サイズ・オフセット）を確認できる

### ✅ 達成: フルパイプライン動作確認
```
テキスト/スクリプト
→ Blender ヘッドレス（約2秒）→ PNG（128×128 RGBA）
→ dat 作成 → makeobj pak128 → .pak
→ Simutrans ゲーム内表示 ✓
```

### TODO
- [ ] より複雑な形状（実際の建物モデル）の生成テスト
- [ ] 4方向で異なる画像を使う（現状は4方向とも同一画像）
- [ ] dat ファイル自動生成との接続（LLM連携）
- [ ] groundobj など他のアドオンタイプへの展開
- [ ] **linter / 静的解析**（別フェーズ）
  - makeobj はパラメーター不足・矛盾をほぼ無視してpak生成する
  - 必須フィールド・値域・type×waytype 組み合わせ妥当性などの検証は
    building_writer.cc 等のソースを精読して linter として実装する
