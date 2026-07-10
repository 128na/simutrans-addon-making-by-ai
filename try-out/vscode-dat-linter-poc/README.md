# dat_linter を VSCode の Problems パネルへ統合する PoC

作業日: 2026-07-10

## 目標

別リポジトリで開発している `dat_linter`（Rust製CLI、`.dat` の静的検証・整形ツール）を、
ESLint のように VSCode の Diagnostics（Problems パネル）へ統合できるか確認する。
最終的には `simutrans-dat-linter` リポジトリのサブディレクトリへ移植する前提の、
使い捨て可能な最小構成の試作として `try-out/vscode-dat-linter-poc/` に作成した。

## 結果

達成。`.dat` ファイルを開く/保存すると `dat_linter lint` を子プロセスで実行し、
出力をパースして `vscode.languages.createDiagnosticCollection` へ反映する拡張を実装し、
`@vscode/test-cli` + `@vscode/test-electron` による自動統合テスト（2件）が通ることを確認した。

## 試したこと

- `try-out/vscode-dat-linter-poc/` に TypeScript 製 VSCode 拡張をスキャフォールド
  - `src/parser.ts`: `dat_linter` の出力1行を正規表現でパースし `vscode.Diagnostic` に変換する純粋関数群（`parseDatLinterLines` / `toVscodeDiagnostics`）
  - `src/extension.ts`: `onDidOpenTextDocument` / `onDidSaveTextDocument` で `.dat` ファイルを検知し、`child_process.execFile` で `dat_linter lint <path> --config <path>` を実行、結果を `DiagnosticCollection` にセット
  - severity マッピング: `error→Error`, `warn→Warning`, `info→Information`, `debug→Hint`
  - 行番号なしの診断は 0 行目（0-indexed）にフォールバック
  - 拡張設定 `datLinterPoc.executablePath`（既定 `dat_linter`）と `datLinterPoc.configPath`（既定は未指定）を用意し、テストからは明示的な `--config` を渡せるようにした
- `@vscode/test-cli`（`.vscode-test.mjs`）+ Mocha で統合テストを実装（`test/extension.test.ts`）
  - `refs/simutrans-dat-linter/testdata/duplicate_key.dat` を開き、`duplicate-key` が Warning・0-indexed line 2（CLI出力は1-indexedの `line 3`）で報告されることを確認
  - `refs/simutrans-dat-linter/testdata/broken_missing_waytype.dat` を開き、`missing-waytype` が Error・行番号フォールバック（line 0）で報告されることを確認
  - `refs/` は参照専用ディレクトリのため、テストはそこにあるファイルを読むだけで書き換えない
- `npm test`（`pretest` で `tsc` コンパイル → `vscode-test` が実VSCodeをダウンロードして起動しテストを実行）で実行し、2件とも pass を確認

  ```
  dat_linter PoC integration
    ✔ duplicate_key.dat produces a duplicate-key Warning on the correct 0-indexed line
    ✔ broken_missing_waytype.dat produces a missing-waytype Error falling back to line 0
  2 passing
  ```

## 得られた知見や失敗

- **最大の落とし穴: `dat_linter lint` は診断本体を stdout ではなく stderr に出力する。**
  stdout に流れるのは末尾の `path: N error(s) / M warning(s)` サマリ行だけで、
  `[warn] duplicate-key (line 3): ...` のような診断行はすべて stderr 行だった。
  事前調査は `2>&1` を付けたターミナルでの手動実行だったため両ストリームが混ざって見えており、
  この違いに気づかなかった。実際に `execFile` で stdout/stderr を分けて受け取って初めて発覚。
  最終的に拡張側では `stdout + "\n" + stderr` を連結してからパースすることで解決した
  （サマリ行は正規表現にマッチしないためパース時に自然に無視される）。
  → **`dat_linter` を外部ツールから呼ぶ実装をする際は、必ず stdout と stderr の両方を
  確認すること。** 手元のターミナル実行結果だけを信用しない。
- **行番号なし診断のフォールバックは問題なく動作した。** `broken_missing_waytype.dat` の
  `missing-waytype`（ファイル全体由来、`(line N)` 部分がない）は 0 行目に正しくマップされた。
  ただし 0 行目に固定するだけだとファイルが長い場合に診断の場所がわかりにくい。今回はPoCの
  範囲外としたが、実運用では「ファイル冒頭にまとめて表示」以上の工夫（例: 該当しそうな
  `obj=` 行を探すヒューリスティック）を検討する余地がある。
- **テキスト出力パースの限界。** `dat_linter` に `--format json` 等の構造化出力オプションは
  無いため、正規表現によるテキストパースに依存している。メッセージ文言や `[severity]` の
  表記が変わると拡張側のパーサも追従が必要で、CLI側との結合度が高い。将来的に
  `dat_linter` 側へ `--format json` を追加してもらう方が保守性は上がりそうだが、今回は
  既存インターフェースのまま統合できることの確認を優先した。
- **`dat_linter.toml` 自動生成の罠は実在した（ただし今回の作業由来ではなかった）。**
  作業開始前に `refs/simutrans-dat-linter/` 直下へ調査目的で `dat_linter lint` を実行した際、
  `--config /dev/null` を渡すつもりが Git Bash 上で意図通り解釈されず、結果的に
  `refs/simutrans-dat-linter/dat_linter.toml` が存在する状態を確認した。ただしファイルの
  mtime を調べたところ本セッション開始より前（2026-07-04）のものであることが判明し、
  今回のコマンド実行で新規生成したものではないと確認できた（`refs/` は gitignore 対象のため
  `git status`/`git log` では判断できず、mtime 比較が必要だった）。
  → **この罠を再発させないため、PoC のテスト・拡張本体は必ず明示的な `--config` を
  渡すようにした。** テスト用設定ファイルは `fixtures/test-lint-config.toml` として用意し、
  拡張の `datLinterPoc.configPath` 設定経由で渡している。
- **`fixtures/dat_linter.toml` という名前は使えなかった。** リポジトリ直下の `.gitignore` に
  `**/dat_linter.toml` という全体一致ルールがあり（`dat_linter` の自動生成物をリポジトリに
  混入させないためのもの）、意図的に作ったテスト用フィクスチャもこのパターンにマッチして
  無視されてしまった。ファイル名を `fixtures/test-lint-config.toml` にリネームして回避した。
- **Windows での `execFile('dat_linter', ...)` 解決は問題なかった。** `dat_linter.exe` は
  `refs/simutrans-dat-linter/target/release/` にあり PATH が通っているが、拡張子なしの
  コマンド名を Node の `child_process.execFile` に渡した場合に PATHEXT 解決されるかが不安点
  だった。実機で単体スクリプトを使って事前検証し、問題なく解決されることを確認した。
- **統合テストの実行コストは軽くない。** `@vscode/test-electron` は初回実行時に実際の
  VSCode（約290MB）をダウンロードして起動するため、初回は数分かかる（2回目以降は
  `.vscode-test/` にキャッシュされるため数秒〜十数秒）。CI に組み込む場合はこのダウンロード
  コストを考慮する必要がある。
