# Blender MCP 使い勝手検証

作業日: 2026-07-23

## 目標
公式Blender MCP（https://projects.blender.org/lab/blender_mcp ）を導入し、
既存のヘッドレスCLIレンダリングパイプライン（`try-out/blender/`）と比較して
対話的なMCP経由操作の使い勝手を確認する。

## 結果
達成

## 試したこと
- Blender公式ページ（blender.org/lab/mcp-server）の手順に沿ってaddonをインストール
  - 通常の `Add-ons` 検索では出てこない（Extensions形式の配布のため）
  - 公式ページからzipをダウンロードし、Blenderウィンドウへドラッグ&ドロップ
    （1回目: Blender Labリポジトリ追加、2回目: addon本体インストール）
- `execute_blender_code` で `try-out/blender/isometric_box.py` と同一ロジックを実行し、
  MCP経由で同じイソメトリックボックスのPNGを生成
- `get_objects_summary` / `get_object_detail_summary` でシーン状態を検査
- `get_screenshot_of_window_as_image` でBlenderウィンドウのスクリーンショット取得を試行
- `render_thumbnail_to_path` で専用サムネイルレンダリングを試行

## 得られた知見や失敗
- **接続経路**: Claude側コネクタ設定だけでは繋がらない。ブリッジプロセス`blender-mcp.exe`が
  動いていても、Blender本体(`blender.exe`)が起動してaddonが有効化されていなければ
  `localhost:9876`への接続はエラーになる
- **addon導入**: 従来のBlender addon（`Edit > Preferences > Add-ons`の検索）ではなく、
  新しいExtensions配布形式。公式ページのzipリンクを手動DLしてドラッグ&ドロップが必要
- **execute_blender_code の使い勝手**: ヘッドレスCLI用に書いた既存スクリプトがほぼそのまま動く。
  ただし`__file__`は使えない（パスは直接指定する必要あり）。戻り値は`result`変数にJSON化して
  代入する規約
- **read系ツールは正確**: `get_object_detail_summary`はscale(0.816)やmaterial名など、
  スクリプトで加えた変更を正確に反映して返す。対話的デバッグに有用
- **get_screenshot_of_window_as_image は今回の環境で常に真っ黒画像を返した**
  （原因未特定。ウィンドウが非フォーカス/最小化状態だと失敗する可能性がある）
- **render_thumbnail_to_path の output_path引数はバグで無視される**。
  指定パスには書き出されず、実際は`%TEMP%\blender_<pid>\blender_mcp\`配下の
  固定ファイル名で出力される。戻り値の`filepath`を必ず確認して読みに行く必要がある
  （ハードコードしたパスをそのまま信用してはいけない）
- **セキュリティ注意（公式ドキュメント明記）**: MCPサーバーはLLM生成コードを
  ガードなしでBlender内で実行するため、データ削除やリモート送信のリスクがある。
  公式はVMまたは機密データにアクセスできない環境での使用を推奨している
- 総評: シーン検査・対話的デバッグ用途では便利。ただし本パイプラインが必要とする
  「決まった手順の一括ヘッドレスレンダリング」用途では、既存の
  `blender --background --python script.py` の方が単純で速く、現状MCPに乗り換える
  積極的な理由は無い（GUI越しの試行錯誤・調査用途向け）
