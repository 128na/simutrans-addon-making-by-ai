# dat linter (PoC) — building dat の静的検証

作業日: 2026-07-01

## 目標
makeobj はパラメーター不足・矛盾をほぼ無視して pak を生成してしまい、
ゲーム内で初めて不具合に気付く → 原因調査に時間がかかる、という問題があった。
これを pak化前に検出する linter を作れるか、まずは比較的シンプルな
`obj=building`（駅拡張建物）に絞って概念検証する。

## 結果
達成。`building_writer.cc` / `get_waytype.cc` / `tabfile.cc` を精読し、
makeobj が黙って見逃す/FATAL ERRORにする項目を6ルールとして実装。
station_test の正常dat・意図的に壊したdat双方で期待通り検出できた。

## 試したこと

### 言語・方式の選定
独立ツール方式（dat構文を静的解析、makeobj非依存）・Rust実装で決定。
理由:
- 将来的にOSS公開し手動作成の作者にも使ってもらう想定があり、単一バイナリで配布できるRustが有利
- 既存の画像系ツール（simutrans-image-merger等）が低速という課題があり、移行の足がかりにしたい
- makeobjのC++ソース改造は二度手間が無い代わりにビルド・upstream追従コストが高く、PoCの段階では見送り

### ソース調査で判明した「サイレントに失敗する」箇所
`building_writer.cc` の `write_obj()` を読むと、以下が**エラーなしで**
不完全な pak を生成することが分かった:
- `cursor`と`icon`が両方とも空文字 → `cursorskin_writer_t`の呼び出し自体が
  スキップされる（`if (!c.empty() || !i.empty())`）。ビルドメニューに表示されない
- 各タイル `[layout][y][x]` に `frontimage`/`backimage` が1枚もない →
  `phases=0`のまま書き込まれ、そのタイルは空画像になる
- `frontimage`の高さ`h>0`は`dbg->error`止まり（fatalではない）→ ログに気付かれず混入しうる
- `type=extension`で`waytype`未指定は「全waytypeに適合する汎用拡張」として
  正当に解釈される（仕様通りだが、意図せずこうなっているケースが多そう）

一方、以下は makeobj 自身が `dbg->fatal` で止めてくれる（サイレントではない）が、
Blender→PNG生成を含むフルパイプラインを回さずに一瞬で検出できる価値はある:
- `type`が未知の文字列、obsolete keyword（`station`/`hall`/`post`/`shed`/`extension_building=1`など）
- `Dims`の`size_x*size_y=0`
- `type=stop`/`type=depot`で`waytype`未指定、または不正な値

加えて、station_test実験で踏んだ次の2つも静的に検出できるようにした:
- 参照画像のサイズが128の倍数でない
- icon/cursor画像の左上(0,0)ピクセルが透過

### 実装構成
```
try-out/dat_linter/
  src/parser.rs       .dat の key=value 読み込み（makeobjのformat_key()を模倣）
  src/diagnostics.rs   Severity(Error/Warning) + Diagnostic
  src/rules.rs         building用検証ルール本体
  src/main.rs           CLI入口（cargo run -- path/to/file.dat）
  testdata/             正常系・意図的に壊した系のテストdat一式
```
ChatGPTから`clap`/`rayon`/`miette`/`tracing`を使った本格構成の提案を受けたが、
単一obj種別のPoCには過剰と判断し採用しなかった（`parser`/`rules`/`diagnostics`の
モジュール分割のみ採用）。複数dat・複数obj種別を一括検証する段階になってから
追加を検討する。

### 動作確認
`testdata/`に作った6パターンで検証:
| ファイル | 期待される検出 | 結果 |
|---|---|---|
| (station_test/station_cube.dat) | 問題なし | OK |
| broken_no_icon.dat | cursor/icon両方欠落 | error 検出 |
| broken_missing_tile.dat | layout 2 のタイル画像欠落 | error 検出 |
| broken_obsolete_type.dat | type=station（obsolete） | error 検出 |
| broken_missing_waytype.dat | type=stopでwaytype欠落 | error 検出 |
| broken_image_size.dat | icon/cursorが64x64 | error 検出 |
| warn_transparent_corner.dat | icon左上が透過 | warning検出（exit 0） |

## 得られた知見や失敗
- makeobjのソースを読むと「デフォルト値で静かに動く」設計が多い
  （例: `obj.get_int("level", 1)`のようにデフォルト引数を取る関数が大半）。
  本当に必須なのは「デフォルトが存在しない/デフォルトのままだと壊れる」項目だけで、
  これは実装前にソースを1ファイルずつ読まないと判別できなかった
- tabfileのキーは大文字小文字を区別しない（`format_key()`で小文字化）ことを
  `tabfile.cc`で確認。dat例で`Dims`/`BackImage`のように大文字が混じっていても
  問題ない理由が裏付けられた
- WindowsにRustツールチェーンが未導入だったため`winget install Rustlang.Rustup`で導入。
  PowerShellツール呼び出しは毎回新規プロセスのため`$env:Path`の変更が次の呼び出しに
  引き継がれず、`cargo`のフルパス（`$env:USERPROFILE\.cargo\bin\cargo.exe`）を
  都度指定する必要があった

## 次回への引き継ぎ
- 現状は`obj=building`の`type=extension`/`stop`/`depot`系のみ対応。
  `vehicle`（shinkansen_0で得た`dat`仕様）や`way`など他obj種別への展開が次の課題
- 画像ファイルの存在チェック・サイズチェックは実装済みだが、makeobjの
  自動クロップ挙動（`image_writer.cc`の`init_dim`）まで踏み込んだ検証
  （例: 透過ピクセルだけで構成された画像で意図しないクロップが起きる）は未実装
- OSS公開を見据えるなら、テストケースを`cargo test`化し、CIで回せるようにする必要がある
