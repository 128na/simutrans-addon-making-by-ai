# pak128 駅拡張建物のフルパイプライン検証

## 目標
Blenderレンダリング→dat作成→makeobj pak化→ゲーム内表示までの一連の流れを確認する

## 結果
達成

## 試したこと
- 128×128px で Blender レンダリング（pak128 タイルサイズに合わせる）
- dat を `type=cur` で作成 → ゲーム内に表示されず
- `cursor` / `icon` フィールドを追加
  - 48×48 のアイコン画像 → `makeobj pak128` がサイズエラー（128の倍数でない）
  - 128×128 に変更してエラー解消
  - 背景透過のアイコン → ゲームが認識しない
  - グレー背景（不透過）に変更
- `type=cur` のまま試行を続けるも表示されず
- 動作確認済みの参照 dat（`refs/building.JpClassicTerminal`）と比較
  - `makeobj VERBOSE DEBUG` で画像読み込みを確認 → 画像自体は問題なし
  - `type=extension` + `waytype=track` + `enables_pax=1` + `NoInfo=1` + `Dims=1,1,4` に変更
  - ゲーム内表示を確認 ✓

## 得られた知見や失敗
- `makeobj pak128` は全画像サイズが **128の倍数** でないとエラー
- アイコン画像の左上(0,0)が透過だとゲームが認識しない
- `cursor` / `icon` がないとビルドメニューに表示されない
- makeobj はパラメーター不足でもエラーを出さない（エラーなし ≠ 正しい）
- `type=station` / `extension_building=1` は makeobj 60.11 では obsolete でビルドエラー
- dat パラメーターの「必須」判断は参照 dat との差分比較で行ったため、どのパラメーターが効いたか未切り分け（linter 実装時に要精査）
- `makeobj VERBOSE DEBUG` が画像の座標・サイズ・オフセットを出力するため問題の特定に有効
