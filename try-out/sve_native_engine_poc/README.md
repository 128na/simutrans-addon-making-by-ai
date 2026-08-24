# sve_analyzer 高速化検証：本家C++エンジンをヘッドレスビルドしてバイナリセーブを直読みするPoC

作業日: 2026-08-24

## 目標

[sve_decompress_bench](../sve_decompress_bench/README.md)で「バイナリ形式のフルパースをゼロから再実装するのは
多日〜数週間規模で非現実的」と判明したことを受け、代替案として**本家Simutrans（`refs/simutrans`）のC++実装を
そのままヘッドレスビルドし、実際のセーブロード処理を流用する**アプローチが成立するか検証する。
ロード後に駅・路線情報をダンプする小さなCLIツールを追加できれば、パース仕様の再実装リスクを避けつつ
デスクトップアプリのバックエンドとして使える可能性がある。

## 結果

達成（アプローチの技術的成立性は実証できた）。ただし2点、実運用に向けて認識すべき制約が見つかった：
1. ヘッドレスビルドの**ランタイムはWindows(MinGW)では正しく動かず、Linux（WSL2）が必要**
2. バイナリセーブは**保存時に使っていたpakset一式（アドオン込み）に依存**しており、
   一致しないと該当オブジェクトが欠落・置換され、最悪`FATAL ERROR`で異常終了する

## 試したこと

### 1. Windows(MinGW-w64)でのヘッドレスビルド

- `winget install MSYS2.MSYS2` → `pacman`で`mingw-w64-x86_64-{gcc,cmake,ninja,zlib,bzip2,libpng,zstd,pkgconf}`を導入。
- `refs/simutrans`はCMakeで`SIMUTRANS_BACKEND=none`という**公式サポートのヘッドレスモード**を持つ
  （Linux専用サーバー向け。`simgraph0.cc`/`simsys_posix.cc`/`no_sound.cc`/`no_midi.cc`という
  「何もしない」描画・音声スタブに差し替えるだけで、ゲームエンジン本体はフルビルドされる）。
- `cmake -G Ninja -DSIMUTRANS_BACKEND=none -DCMAKE_TOOLCHAIN_FILE= -DSIMUTRANS_USE_REVISION=99999 ..`
  （`CMAKE_TOOLCHAIN_FILE=`で不要なvcpkgトリプレット要求を回避、`SIMUTRANS_USE_REVISION`で
  gitリビジョン自動検出失敗を回避）で**ビルド成功**（336ターゲット全て）。
- しかし実行すると`Simutrans version ...`を出力した直後で**ハング**（メモリ使用量変化なし、強制終了必須）。
  `simsys_posix.cc`はLinux専用サーバー向けのPOSIXバックエンドで、MinGW/Windows環境での動作は
  想定されていないと推測される。

### 2. WSL2 (Ubuntu-26.04) でのヘッドレスビルド

- `sudo apt-get install build-essential cmake ninja-build zlib1g-dev libbz2-dev libzstd-dev libpng-dev pkg-config`
  （sudoパスワード入力はエージェントでは行えないため、ユーザーに実行してもらった）。
- 同じCMake設定でビルド成功。**今度はハングせず正常に動作**。

### 3. 実セーブデータのロード検証

- `-load`は**`<user_dir>/save/`配下のファイル名（拡張子省略可）を前提に`save/`を自動的に前置する**
  仕様（`simmain.cc`の`SAVE_PATH_X "%s"`）。絶対パスを直接渡すと`save//絶対パス`という
  存在しないパスを探しに行って静かに失敗する（＝ワールドが空のまま起動するだけで、エラーで
  落ちるわけではないので気づきにくい）。検証時は対象ファイルを`<user_dir>/save/`にコピーし、
  拡張子なしのbasenameを渡す必要があった。
- `refs/save/#00 kuma-1930-3.sve`（1930年、初期セーブ）をロード → **完全に成功**。
  ログで`init 24 cities`→`loading tiles`（タイル/オブジェクトグラフの全走査）→
  `921 ways loaded`→`0 halts loaded`（この時点でまだ駅を作っていないため0件は妥当）→
  `players loaded`まで完走し、その後の自動セーブでも`saved tiles`/`saved stops`/`saved players`
  まで正常に書き戻せた。バイナリ形式で最大の懸念だった「30種類以上のオブジェクト型の
  ディスパッチを伴うタイル走査」が、本家実装を使うことで一切の再実装無しに正しく動くことを実証。
- `refs/save/#17 kuma-2009-9.sve`（2009年、120都市の大規模セーブ）でも試したところ、
  タイル走査自体は最後まで進行した（ログ11万行超）ものの、`wa-cs-platform-1`や`wa-cs-frame`
  など**このリポジトリのpak128（`simuwin/pak128`）に存在しないオブジェクト参照**が多数見つかり、
  最終的に`FATAL ERROR: Maximum 15 grounds at 288,99 exhausted`で異常終了した。
  `simuwin/addons/pak128`（本リポジトリ独自の実験用アドオン置き場）にも該当オブジェクトは無く、
  この特定のセーブは保存時に別のアドオンパックセット（"wa-cs-"系、林鉄/森林鉄道系アドオンと
  推測）を使っていたため、それを用意しない限り再現できない。

## 得られた知見や失敗

- **本家エンジンの流用は技術的に成立する**: 事前の懸念（`karte_t::laden()`がGUI/描画系に直接依存）は
  正しかったが、`SIMUTRANS_BACKEND=none`という公式ヘッドレスモードがまさにその依存を切り離すために
  存在しており、ゲームエンジン全体をそのままビルドしてロード/セーブのみ使う、という発想が現実的に
  機能した。バイナリ形式のオブジェクトグラフを自前で再実装するリスク（[前回のPoC](../sve_decompress_bench/README.md)で
  多日〜数週間規模と判明）を完全に回避できる。
- **プラットフォームはLinux必須**: 同じソース・同じCMakeオプションでもWindows(MinGW)ではランタイムが
  ハングし、WSL2(Ubuntu)では正常動作した。デスクトップアプリ化する場合、Windows上で完結させたいなら
  ①WSL2をバックエンドとして呼び出す、②ヘッドレスバックエンドをWindows向けに手直しする、
  のいずれかが必要になる。
- **`-load`の絶対パス指定は静かに失敗する**: エラーで落ちずワールドが空のまま起動するため、
  「動いているように見えて実は何もロードできていない」という罠がある。実装時は`<user_dir>/save/`に
  配置する前提で設計するか、ソース側にパス指定の修正パッチを当てる必要がある。
- **バイナリセーブはpakset依存が強い**: 保存時に使っていたベース+アドオンpaksetが完全に揃っていないと、
  オブジェクトの欠落・置換が起き、最悪ロードが異常終了する。これは自前実装でもエンジン流用でも
  避けられない、バイナリ形式そのものの制約（ゲーム本体が要求するのと全く同じ制約）である。
  デスクトップアプリとして配布する場合、駅・路線情報の抽出だけが目的でも「ロード可能にするための
  正しいpakset一式」を用意する運用が必要になる。
- **次のステップ**: 現状は`-load`後に`-server`相当の常駐ループに入ってしまい、SIGTERMで止めるまで
  終了しない。実用ツールにするには`simmain.cc`（または`karte_t`）に「ロード直後に
  `welt->get_haltestelle_liste()`・各`spieler_t::get_linemgmt()`から駅・路線情報を集めてJSON等に
  ダンプし、即座に`exit()`する」ワンショットモードを追加する小さなパッチが次の作業になる。
  ビルド・ロードの土台自体はここまでで確立できている。
