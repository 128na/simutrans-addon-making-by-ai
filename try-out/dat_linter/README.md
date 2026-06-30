# dat linter (PoC) — building dat の静的検証

作業日: 2026-07-01

## 目標
makeobj はパラメーター不足・矛盾をほぼ無視して pak を生成してしまい、
ゲーム内で初めて不具合に気付く → 原因調査に時間がかかる、という問題があった。
これを pak化前に検出する linter を作れるか、まずは比較的シンプルな
`obj=building`（駅拡張建物）に絞って概念検証する。
あわせて、各ルールが本当にソースコードで裏付けられているか、本体アップデートや
有志フォーク（OTRP）にも通用するかも検証する。

## 結果
達成。`building_writer.cc` / `get_waytype.cc` / `tabfile.cc` を精読し、
makeobj が黙って見逃す/FATAL ERRORにする項目をルール化。
station_test の正常dat・意図的に壊したdat双方で期待通り検出できた。
実装後の見直しで、根拠不明だったルールを1件削除し（後述）、
OTRPフォークでも同じロジックが通用することをソース比較で確認した。

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

加えて、station_test実験で踏んだ「参照画像のサイズが128の倍数でない」も
`image_writer.cc`の`if ((w%img_size!=0)||(h%img_size!=0)) dbg->fatal(...)`で
裏付けが取れたため実装した。

一方、同じくstation_test実験由来の「icon/cursor画像の左上(0,0)ピクセルが透過だと
ゲームが認識しない」というルールは、後日`simutrans`ソース全体を検索しても該当ロジックが
見つからず、実装から**削除**した（詳細は「得られた知見や失敗」参照）。

### ログレベル
4段階の `Severity` を導入し、列挙の宣言順がそのまま重大度（高い順）になるよう
`derive(PartialOrd, Ord)` で表現した。`severity <= 表示level` で「そのlevelで表示すべきか」を判定する。

| level | 用途 |
|---|---|
| error | pak化に失敗する、ゲーム内で正常に表示されない |
| warn | 非推奨な項目、動作はするが設定が推奨される項目 |
| info | 正常な項目の簡易な出力（各チェックの合格確認） |
| debug | 詳細な監査ログ（生の値・解決後のパス・索いたキー名など） |

デフォルトは `error`+`warn` のみ表示（壊れたdatを素早く確認する用途）。
`-v` で `info` まで、`-vv` で `debug` まで表示する。
exit code は `error` が1件でもあれば1、それ以外（warnのみ含む）は0
（makeobj自身がfatalにする/しないの区別に対応させた）。

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
`testdata/`に作った正常系1 + 異常系5パターンで検証:
| ファイル | 期待される検出 | 結果 |
|---|---|---|
| (station_test/station_cube.dat) | 問題なし | OK |
| broken_no_icon.dat | cursor/icon両方欠落 | error 検出 |
| broken_missing_tile.dat | layout 2 のタイル画像欠落 | error 検出 |
| broken_obsolete_type.dat | type=station（obsolete） | error 検出 |
| broken_missing_waytype.dat | type=stopでwaytype欠落 | error 検出 |
| broken_image_size.dat | icon/cursorが64x64 | error 検出 |

### 検査項目の妥当性の裏付け、OTRP（有志フォーク）対応の検証
全ルールについて、ソースコード上の根拠を再確認した:
- 8ルール中7ルールは`building_writer.cc`/`get_waytype.cc`/`image_writer.cc`の
  該当箇所を直接特定できた（`image-size-not-multiple-of-128`はこの見直しで
  `image_writer.cc:270-272`を特定し裏付けが取れた）
- 1ルール（icon/cursor左上ピクセル透過）は根拠コードが見つからず削除した。
  station_test実験当時「直った」と感じた原因が別だった可能性がある

OTRP（Simutrans-Extended系の有志フォーク, https://github.com/teamhimeh/simutrans ）を
クローンして`building_writer.cc`/`get_waytype.cc`/`tabfile.cc`相当を比較した結果、
building dat の検証に関わるロジック（type/waytype一覧、cursor/icon省略時の挙動、
タイル画像欠落時の挙動、Dims size=0判定、画像サイズ128の倍数判定、キーの大文字小文字非区別）は
**vanilla simutransと完全に一致**していた（差分はバイナリnodeフォーマットの版数のみ）。
そのため、現在の7ルールはOTRP向けdatにもそのまま使える（検証コミット:
vanilla `1d2799f9a7`、OTRP `d6d3a5795b`、共に詳細は`rules.rs`冒頭コメント参照）。

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
- 「station_testで効果があった」という経験則をそのままルール化するのは危険。
  左上ピクセル透過ルールはソースに根拠が見つからず削除した。経験則は「現象の記録」
  であって「原因の特定」ではないため、linterのような断定的な検査ルールに採用する前に
  ソースコードでの裏付けを必須にすべきだった
- OTRP対応について、定数表を外部データファイル化してフォーク別に切り替えられる
  「dialect」機構を作ることも検討したが、実際にdiffした結果vanillaと完全一致だったため
  見送った。差分が存在しないのに切り替え機構だけ先に作るのは過剰設計と判断した
  （CLAUDE.mdの「将来の仮説的要件のために設計しない」方針に合わせた）

## 次回への引き継ぎ
- 現状は`obj=building`の`type=extension`/`stop`/`depot`系のみ対応。
  `vehicle`（shinkansen_0で得た`dat`仕様）や`way`など他obj種別への展開が次の課題
- 画像ファイルの存在チェック・サイズチェックは実装済みだが、makeobjの
  自動クロップ挙動（`image_writer.cc`の`init_dim`）まで踏み込んだ検証
  （例: 透過ピクセルだけで構成された画像で意図しないクロップが起きる）は未実装
- OSS公開を見据えるなら、テストケースを`cargo test`化し、CIで回せるようにする必要がある
- OTRP対応は今回「現状ロジックがそのまま通用する」ことを確認しただけで、
  OTRP独自のobjタイプ・フィールド（斜め線路駅設置など）には触れていない。
  vehicle/way等への対応を広げる際に、その都度OTRP側ソースとも突き合わせること
- 本体側（vanilla）・OTRP側のどちらかが更新されたときに定数表が古くなっていないか
  気付く仕組みがない。サブモジュール更新時のチェックリスト化、または
  `rules.rs`冒頭コメントの検証コミットと現在のサブモジュールコミットを
  比較する簡易テストの追加を検討する
