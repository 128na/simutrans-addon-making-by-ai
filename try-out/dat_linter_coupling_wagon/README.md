# dat_linter による連結制約(Constraint)付きvehicle dat作成の実地検証

作業日: 2026-07-05

## 目標

新しく整備された `dat_linter`（Rust製、PATH通し済み）が、ミスが起きやすい複雑な
vehicle(車両) dat仕様——特に方向別画像(emptyimage)・複数積載レベルの貨物画像
(freightimage/freightimagetype)・連結制約(Constraint[Prev]/Constraint[Next])——の
作成をどれだけスムーズにしてくれるかを、意図的なミスの仕込みと検出サイクルを通じて
実地検証する。画像は既存の `station_cube.png`（128x128 RGBA）を全スロットで使い回し、
焦点はdatの構造とツールの使い勝手そのものに置いた。

## 結果

達成

- 2両編成（機関車 TestLoco + 貨車 TestWagon）のvehicle datを作成し、8方向の
  emptyimage、2段階積載(空/満載)×8方向のfreightimage、Constraint[Prev]/[Next]に
  よる連結制約を一通り実装。
- 意図的な4種類のミスをすべてdat_linterが検出できることを確認（詳細は下記）。
- `dat_linter fmt -w` によるフォーマットも実施し、差分を確認。
- `makeobj pak128` によるビルドも成功（`testconsist.pak` 852,625 bytes 生成）。

## 試したこと

### 0. ベースライン作成

`try-out/dat_linter_coupling_wagon/` に `loco.dat`（機関車、Constraint[Next][0]=TestWagon）
と `wagon.dat`（貨車、Constraint[Prev][0]=TestLoco、freight=Kohle、freightimage[0]/[1]の
2段階積載を8方向）を作成。`station_cube.png` を同ディレクトリへコピーして全画像スロットで
使い回した。

作成時、`wagon.dat` の `engine_type=none` が `unknown-engine-type` 警告
（「makeobjはfatal/errorを出さずdieselにフォールバックする」旨）を出したため、
`engine_type=diesel` に修正してクリーンなベースラインを確立した。

`dat_linter lint .` と `dat_linter analyze . --kind coupling` を
**try-outディレクトリから実行した場合とリポジトリルートから実行した場合の両方**で確認したが、
出力内容（パス表記以外）に差異はなかった。`dat_linter.toml` の自動検出はカレントディレクトリの
違いに関わらず一貫していた。

### a) freightimagetype[1] を書き忘れる

`wagon.dat` の `freightimagetype[1]=Kohle` を削除して `dat_linter lint .` を実行。

```
.\wagon.dat: [error] missing-freightimagetype: freightimagetype[1] is unspecified. Since 2 indexed freightimage entries are used, freightimagetype[i] (an xref to a good) is required for each index (makeobj treats this as a FATAL ERROR)
```

想定通り`missing-freightimagetype`が検出された。修正して再実行し、exit code 0（クリーン）に
戻ることを確認。

### b) freightimage[1][...] を8方向中4方向だけにする

`freightimage[1][se]`, `[sw]`, `[w]`, `[nw]` の4行を削除して `dat_linter lint .` を実行。

```
.\wagon.dat: [error] missing-indexed-freightimage: freightimage[1][w] is unspecified. ...(makeobj treats this as a FATAL ERROR)
.\wagon.dat: [error] missing-indexed-freightimage: freightimage[1][sw] is unspecified. ...
.\wagon.dat: [error] missing-indexed-freightimage: freightimage[1][se] is unspecified. ...
.\wagon.dat: [error] missing-indexed-freightimage: freightimage[1][nw] is unspecified. ...
4 error(s) / 0 warning(s)
```

事前情報にあった`freightimage-count-mismatch`ではなく`missing-indexed-freightimage`が
欠けている方向ごとに個別に4件出力された。修正して再実行しクリーンに戻ることを確認。

### c) wagon.dat の Constraint[Prev][0] にタイポ（存在しない名前）を入れる

`Constraint[Prev][0]=TestLoco` を `Constraint[Prev][0]=TestLocoo`（タイポ）に変更。

- `dat_linter lint .` → **検出せず（exit 0）**。これは想定通りで、danglingなxref検証は
  lintの担当範囲外であり、analyzeコマンドの仕事であることが確認できた。
- `dat_linter analyze . --kind coupling` →

```
.: [error] dangling-vehicle-constraint: TestWagon (.\wagon.dat): the vehicle "TestLocoo" referenced by constraint[prev] does not exist in this directory (makeobj does not validate reference existence, so this goes unnoticed until the game loads it)
.: [error] unsatisfiable-constraint: TestLoco (.\loco.dat): no finite consist satisfying constraint[prev]/constraint[next] can be assembled ...
.: [error] unsatisfiable-constraint: TestWagon (.\wagon.dat): no finite consist satisfying constraint[prev]/constraint[next] can be assembled ...
3 error(s) / 0 warning(s)
```

`dangling-vehicle-constraint`が期待通り検出された。加えて、タイポの副作用として
`unsatisfiable-constraint`が両車両に連鎖的に出た点が興味深い
（TestWagonが実在しないTestLocooを要求する結果、実質的にどの車両とも編成が組めなくなるため、
充足可能性チェックにも波及する）。修正して再実行し両コマンドともクリーンに戻ることを確認。

### d) loco/wagonのConstraintを矛盾させ、有限編成が成立しない状態を作る

`wagon.dat` の `Constraint[Next][0]=none` を `Constraint[Next][0]=TestLoco` に変更
（貨車の前後どちらもTestLocoを要求する状態＝ TestLoco-TestWagon-TestLoco-TestWagon-...
と無限に連結しないと条件を満たせない）。

```
.: [error] unsatisfiable-constraint: TestLoco (.\loco.dat): no finite consist satisfying constraint[prev]/constraint[next] can be assembled ...
.: [error] unsatisfiable-constraint: TestWagon (.\wagon.dat): no finite consist satisfying constraint[prev]/constraint[next] can be assembled ...
2 error(s) / 0 warning(s)
```

想定通り両車両に`unsatisfiable-constraint`が出た。修正して再実行しクリーンに戻ることを確認。

### fmt によるフォーマット・並び替え確認

すべてのミス修正後、`dat_linter fmt try-out/dat_linter_coupling_wagon -w` を実行。
オリジナルと比較した差分:

- 数値系フィールド（cost, payload, speed, weight, axle_load, power, runningcost,
  maintenance, intro_year）を前方に、waytype/engine_typeを後方に並び替え
- `Constraint[Prev][0]` / `Constraint[Next][0]` → `constraint[prev][0]` /
  `constraint[next][0]` と小文字化して正規化（併せて next→prev の順で並び替え）
- `emptyimage[dir]` / `freightimage[N][dir]` の方向をアルファベット順
  （e, n, ne, nw, s, se, sw, w）に並び替え（元は手で書いた n, ne, e, se, s, sw, w, nw
  の時計回り順だった）
- `freightimagetype[N]` を対応する `freightimage[N][...]` 群の直前に移動し、
  indexごとにグルーピング

フォーマット後も `dat_linter lint .` は exit code 0 でクリーン。

### makeobj ビルド確認

```
cd try-out/dat_linter_coupling_wagon
makeobj pak128 testconsist.pak loco.dat wagon.dat
```

`Reading file loco.dat / packing vehicle.TestLoco`、
`Reading file wagon.dat / packing vehicle.TestWagon` と出力され、
`testconsist.pak`（852,625 bytes）が正常に生成された（exit 0）。
ゲーム内での実機確認までは対象外。

## 得られた知見や失敗

- **検出精度は高い**: 事前調査で想定していた4種のミス（missing-freightimagetype,
  missing-indexed-freightimage, dangling-vehicle-constraint, unsatisfiable-constraint）
  すべてを、まさに期待したコードで検出できた。誤検知・見逃しは無かった。
- **メッセージの実用性が高い**: 単に「不正」と言うだけでなく、「makeobjはこれをFATAL ERROR
  として扱う」「makeobjは参照の実在性を検証しないため、ゲームがロードするまで気づかれない」
  など、**makeobj側の挙動との対比**を明記している点が非常に有用。CLAUDE.mdにある
  「makeobjはパラメーター不足でもエラーを出さない（エラーなし≠正しい）」という既知の罠を、
  dat_linterのメッセージ自体が補強してくれている。
- **lintとanalyzeの責務分担が明確**: (c)のdanglingタイポ実験で、lintは無反応・analyzeのみが
  検出したことで、「datファイル単体の静的検証(lint)」と「ディレクトリ横断のグラフ整合性検証
  (analyze --kind coupling)」の境界がツールの動作から体感的に理解できた。これは事前情報だけ
  では実感しづらかった点で、実地検証の価値があった。
- **1つのミスが複数の診断を誘発することがある**: (c)のタイポでは`dangling-vehicle-constraint`
  に加えて`unsatisfiable-constraint`も両車両に連鎖して出た。これは「タイポにより実質的に
  編成が組めなくなる」という意味では正しい副作用だが、初見だと「なぜ無関係なloco.datまで
  エラーが出るのか」と戸惑う可能性がある。ルート原因（danglingの参照）とその波及効果
  （satisfiability破綻）を分けて捉える必要があり、メッセージを読む側に多少の慣れが要る。
  ツール側の問題というよりは連結制約という仕様自体の複雑さに起因する。
  ただ、両方とも「今回仕込んだ唯一のミス」に起因する妥当な検出であり誤検知ではない。
  以降さらに使い込む場合は、まず`dangling-vehicle-constraint`から潰すと
  `unsatisfiable-constraint`も連動して消えることを覚えておくと効率的。
- **fmtの並び替えは妥当かつ実務的**: フィールドの並び順、Constraintキーの大文字小文字統一、
  方向のアルファベット順ソート、freightimagetypeのグルーピングは、いずれも人間が手で書く際に
  ブレやすい箇所であり、fmtによる正規化は複数人（あるいはAIエージェント）が関わる編集を
  安定させる効果が期待できる。ただし元のemptyimage方向順（n, ne, e, se, s, sw, w, nw の
  時計回り）は視覚的に理解しやすい順序だったのに対し、fmt後のアルファベット順
  （e, n, ne, nw, s, se, sw, w）は機械的で意味的な直感には乏しい。どちらが良いかは好みの
  問題だが、「fmtを適用すると意味的な並びが失われる」点は認識しておくべき。
  （もっとも、diff安定性・grep容易性の観点ではアルファベット順に利点がある）
  なお`fmt`実行時、`Constraint`→`constraint`の大文字小文字変更が「並び替え」以外の
  変更として混在していたのは少し意外だった（fmtは並び替えだけでなくキー名の正規化も行う）。
- **実行ディレクトリによる差異は無し**: try-outディレクトリからでもリポジトリルートからでも
  `dat_linter.toml`の自動検出・診断結果に差異は見られなかった。カレントディレクトリを
  気にせず呼び出せる点は運用上安心材料になる。ただし、try-outディレクトリから初回実行した際に
  そのディレクトリ内にも`dat_linter.toml`（リポジトリ直下のものと同一内容のデフォルト設定）が
  自動生成される副産物があった。リポジトリ直下の`dat_linter.toml`は`.gitignore`で`/dat_linter.toml`
  として無視されるが、サブディレクトリ内の生成物はこのパターンにマッチせず`git status`に
  未追跡ファイルとして現れる。今回は実験の本質的成果物ではないため削除した。
  サブディレクトリ単位で`dat_linter`をよく実行する運用にする場合は、`.gitignore`のパターンを
  `**/dat_linter.toml`のように広げるか、常にリポジトリルートから実行する運用にするかを
  検討した方がよい。
- **副次的な気づき**: Readツール（Claude Code内蔵）が`.dat`をバイナリファイルと誤認識し
  読み込みを拒否した（実体はプレーンテキスト）。dat_linter自体の問題ではないが、
  AIエージェントがdatファイルを直接読み書きする際はテキストエディタ的操作
  （Bash経由のcat/sed等）を使う必要がある点は運用上のノウハウとして記録に値する。
- **makeobjビルドも成功**: 意図的なミスをすべて修正した最終状態のdatは、
  `makeobj pak128`でも問題なくビルドできた。dat_linterの「クリーン」判定と
  makeobjの実際のビルド成功が一致しており、事前検証ツールとしての信頼性を確認できた。
