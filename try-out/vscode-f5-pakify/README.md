# VSCode上でmakeobjを認識させF5でpak化する

作業日: 2026-07-13

## 目標
VSCodeで`.dat`ファイルを開いた状態でF5（実行）を押すと、`makeobj pak128`が
そのファイルに対して実行され`.pak`が生成される、という開発体験を実現する。

## 方針（A案: ワークスペース設定のみで実現）
拡張機能のコード変更は不要。VSCode標準の`launch.json`（`node-terminal`タイプ、
Node.js Debugging組み込み拡張が提供、追加インストール不要）と`tasks.json`を
リポジトリルートの`.vscode/`に置くだけで実現する。

`node-terminal`タイプは「デバッガではなく、統合ターミナルで任意のコマンドを実行する」
という汎用launch設定として使える。`${fileDirname}`/`${fileBasename}`/
`${fileBasenameNoExtension}`というVSCode組み込み変数で、現在アクティブなエディタの
ファイルパスを参照できる。

## 結果
継続中（コマンド自体の動作確認は完了、VSCode上でのF5実際の挙動は未確認）

## 試したこと
- `try-out/station_test/station_cube.dat`を対象に、実際に生成予定のコマンド
  （`makeobj pak128 station_cube.pak.test station_cube.dat`、cwd=station_test/）を
  手動実行し、`.pak`が正しく生成されることを確認済み
- `.vscode/tasks.json`（リポジトリルート）に「makeobj: 現在の.datをpak化」
  「makeobj: 現在の.datをpak化（詳細ログ）」の2タスクを追加
  （`type: "shell"`、`command: "makeobj"`、`cwd: "${fileDirname}"`）
- `.vscode/launch.json`（リポジトリルート）に対応する`node-terminal`タイプの
  launch設定を2件追加。F5でデフォルト設定（詳細ログ無し版）が実行される

## 得られた知見や失敗
- `makeobj`は`C:\bin\makeobj.exe`としてPATHに既に通っている環境だった（今回の検証では
  インストール手順は不要だった）
- `node-terminal`はNode.js Debugging組み込み拡張が提供する標準機能のため、追加の拡張機能
  インストールなしでF5からの任意コマンド実行が可能
- VSCodeのF5キー押下自体の実機確認はこのセッションでは実施できていない
  （ターミナル経由の操作のみでVSCode UIを直接操作できないため）。ユーザー自身に
  実際にF5を押して動作確認してもらう必要がある

## 今後の検討（アドオン作者は非エンジニアという前提での配布方法）
`.vscode/`をこのリポジトリのように手作業で書ける前提は、非エンジニアのアドオン作者には
成立しない。今回の仕組みが実際に動くと確認できたら、以下のような配布・自動セットアップの
検討が必要（このタスクの範囲外、フォローアップとして記録）:
- **Claude Codeスキル**: アドオン作者がClaude Codeでプロジェクトを開いた際に、
  makeobjの導入確認・`.vscode/tasks.json`/`launch.json`のスキャフォールドを
  自動で行うスキル
- **インストーラー**: Claude Code非依存で、makeobj本体の配置＋VSCode設定ファイルの
  配置を一括で行うスタンドアロンのインストーラー（GUI/スクリプト）
