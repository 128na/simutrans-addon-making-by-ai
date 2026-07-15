# Knowledge

## Simutrans イソメトリック仕様
参考: https://ahozura.kasu.me/portal/?p=666 （Metasequoiaでの制作手順）

- カメラ種類: 直交投影 (Orthographic)
- 仰角 (pitch): **30°** → Blender X rotation = 60°
- 方位角 (head): 45°（SE視点）、他方向は 135°/225°/315°
- 高さスケール: **X:Y:Z = 100:81.6:100**（height = side × √6/3 ≈ 0.816）
- タイルサイズ: pak128 = 128×64px / タイル（2:1比率）
- 側面が暗い場合: 自己発光 0.2〜0.3 を設定する

## Blender ヘッドレスレンダリング

**実行コマンド**
```
blender --background --python script.py
```

**Blender 5.1.x 固有の注意**
- render engine: `'BLENDER_EEVEE'`（`BLENDER_EEVEE_NEXT` は 4.x 系の名称）
- `use_nodes` は Blender 6.0 で削除予定だが 5.x では動作する

**カメラ設定パターン**
```python
cam.data.type = 'ORTHO'
cam.data.ortho_scale = math.sqrt(2)  # 1×1 BUタイルを128pxにぴったり収める
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

# カメラ位置はrotationから逆算（手動で設定するとフレームがズレる）
bpy.context.view_layer.update()
target = mathutils.Vector((0, 0, z_center))
forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
cam.location = target - forward * distance
```

**ortho_scale と解像度の関係**
- 1タイル = 1×1 BU とする
- `ortho_scale = tile_side × √2` で Nタイル幅なら `N × √2`
- 1 BU ≈ 90.5px（非整数だが公式はシンプル）

**透過PNG出力**
```python
scene.render.film_transparent = True
scene.render.image_settings.color_mode = 'RGBA'
```

**タイル境界と一致する形状は4倍supersample+アルファ二値化でアンチエイリアスの
半透明エッジを消す**
- タイル全面を覆う平面（道路等）のように、レンダリングする形状の輪郭が「タイルの
  外周そのもの」と一致する場合、Blenderのアンチエイリアスによってその輪郭が
  半透明ピクセルとしてレンダリングされる。Simutransは隣接タイルを単純合成するため、
  この半透明ピクセルから下の地面（芝生等）がうっすら透けて見え、タイルを連続設置した
  ときに継ぎ目に薄い隙間があるように見える不具合が起きる（`try-out/way_flat_test/`で
  ユーザー実機確認により発見）
- 対策: 目標解像度(128x128)の4倍(512x512)でレンダリングしてから
  `Image.resize((128,128), Image.LANCZOS)`で縮小し、縮小後にアルファチャンネルを
  閾値(例:128)で0/255の二値にハード処理する。半透明ピクセルを完全に排除できる
  （実装例: `try-out/way_flat_test/postprocess.py`。Blender本体のPython環境に
  PILが無い場合があるため、後処理はBlender外の素のPythonで行うのが手軽）
- 建物(building)のような、タイル境界まで届かない孤立した形状（余白がある）では
  この問題は基本的に起きない。輪郭が実際にタイル境界と接する形状（道路のような
  全面カバー系、線路の直線区間の両端等）でのみ必要な対策

**カメラ注視点Zは「オブジェクトの高さ」ではなく固定の地面アンカー**
- 注視点(target)のZ座標は常に `0.408`（= 1フロア相当の高さ0.816の半分）に固定する。
  これは「レンダリングするオブジェクトの中心」ではなく、キャンバス内で地面がどのpx行に
  来るかを決める固定アンカーであり、オブジェクト自身の高さとは無関係
- `try-out/way_flat_test/`で高さほぼ0の平面(道路)・薄いbox(線路)をこの理解なしに
  「オブジェクト自身の中心」でtargetを設定して(道路はz=0、線路は物体高さの半分)
  レンダリングしたところ、ゲーム内でタイル上空32pxに浮いて表示される不具合が発生。
  target.zを一律0.408に直すことで解消した
- 検証済みの立体物（isometric_box.py・station_cube.png、いずれも高さ0.816のcubeで
  target.z=0.408）はたまたま「オブジェクトの中心」と「固定アンカー0.408」が一致する
  高さだったため、この違いが表面化していなかった
- 逆算の根拠: 観測されたズレ32pxを`px_shift = world_z_shift × 0.866 × (128/ortho_scale)`
  （0.866=cos30°、`ortho_scale=√2`時の`128/ortho_scale`≈90.5px/BU）に当てはめると
  `world_z_shift ≈ 0.408`となり、target.zを0→0.408に補正する量とほぼ一致する

**px単位で寸法を指定したい場合のBU変換係数（カメラ: ortho_scale=√2, rotation=(60°,0,45°)）**
- 道路のセンターラインや線路の道床/レールのような「実物のpak128画像を見て px単位で
  微調整したい」細い寸法は、BU相対値ではなくpxで直接指定してからBUへ変換する方が
  フィードバックを反映しやすい（`try-out/way_flat_test/`のrender_rail.py参照）
- 変換係数は`cam.matrix_world.to_3x3()`のright/up基底ベクトルと世界軸との内積を実測して
  導出できる（`cam.matrix_world.to_3x3() @ Vector((1,0,0))`等をprintするprobeスクリプトを
  一時実行）。このカメラ設定での実測値:
  - 世界Z軸（縦方向の高さ）: `1 BU = (128/√2) × cos(30°) ≈ 78.38 px`
  - 世界X軸・Y軸（横方向のオフセット、どちらも同じ）: `1 BU = (128/√2) × cos(45°) = 128/2 = 64.0 px`
    （ちょうど半分になるきれいな値）
  - 上記はいずれも「画面のどちらか一方の軸（縦 or 横）への投影量」であり、世界X/Y軸の
    オフセットは実際には画面の縦横両方に斜めに投影される（例: 世界X軸1BUは画面横+64px・
    画面縦-32px、世界Y軸1BUは画面横+64px・画面縦+32px）。「純粋に画面横方向だけの
    ズレ」を作りたい場合は世界X軸とY軸を同じ比率で混ぜる必要がある点に注意

**画面上の位置補正は、薄い形状に対してはZ(高さ)ではなくX/Yの組み合わせで行う方が安全**
- 画面上でn px下に動かしたいとき、直感的には対象のworld Zを`n / 78.38`だけ減らせば
  よさそうに見えるが、対象が薄い形状（道床+レールのような数px高の物体）の場合、
  この量がすぐに物体自身の高さを超えてしまい、隣接する不透過なオブジェクト（道床など）
  の内部・下面より下に潜り込んで完全に隠れ、レンダリング結果から消失する事故が起きる
  （`try-out/way_flat_test/`で実際に発生: 奥側レールを3px分Zで下げたところ道床の下に
  潜り込み、ゲーム内で非表示になった）
- 安全な代替策: Zは一切変えず、world X/Yを**逆符号で同じ量だけ**動かすと、画面横方向
  (dx)の変化を打ち消しながら画面縦方向(dy)だけを動かせる。上記の投影量を使うと
  `dx = 64a + 64b`, `dy = -32a + 32b`（a=Xオフセット, b=Yオフセット, 単位BU）なので、
  `b = -a`とすれば`dx=0`、`dy = -64a`となり、`a = n_px / 64`で画面n_px下方向への
  純粋な移動が得られる（Zは触らないので他オブジェクトへの埋没リスクがない）

**タイル境界と一致する形状は4倍supersample+アルファ二値化でアンチエイリアスの
半透明エッジを消す**
- タイル全面を覆う平面（道路等）のように、レンダリングする形状の輪郭が「タイルの
  外周そのもの」と一致する場合、Blenderのアンチエイリアスによってその輪郭が
  半透明ピクセルとしてレンダリングされる。Simutransは隣接タイルを単純合成するため、
  この半透明ピクセルから下の地面（芝生等）がうっすら透けて見え、タイルを連続設置した
  ときに継ぎ目に薄い隙間があるように見える不具合が起きる（`try-out/way_flat_test/`で
  ユーザー実機確認により発見）
- 対策: 目標解像度(128x128)の4倍(512x512)でレンダリングしてから
  `Image.resize((128,128), Image.LANCZOS)`で縮小し、縮小後にアルファチャンネルを
  閾値(例:128)で0/255の二値にハード処理する。半透明ピクセルを完全に排除できる
  （実装例: `try-out/way_flat_test/postprocess.py`。Blender本体のPython環境に
  PILが無い場合があるため、後処理はBlender外の素のPythonで行うのが手軽）
- 建物(building)のような、タイル境界まで届かない孤立した形状（余白がある）では
  この問題は基本的に起きない。輪郭が実際にタイル境界と接する形状（道路のような
  全面カバー系、線路の直線区間の両端等）でのみ必要な対策

**上記の半透明対策だけでは境界に色みの差（フリンジ）が残ることがあり、原因は2段階ある**
- 原因1: 透明領域のRGBはBlenderの背景色である黒(0,0,0)のまま保存されている。
  LANCZOS等で縮小するとき「不透明な物体色」と「透明領域の黒」を混ぜてしまうため、
  輪郭のすぐ内側にオーバーシュート/アンダーシュート（リンギング）が生じ、境界だけ
  明るく/暗くなって見える。対策: 縮小前に透明領域のRGBを最も近い不透明ピクセルの色
  で塗りつぶす(color bleed/dilate)。numpyで8近傍平均を複数回繰り返す簡易実装で十分
- 原因2（見落としやすい）: 原因1の対策（RGBの塗りつぶし）をしても直らないことがある。
  これは`PIL.Image.resize()`がRGBA画像に対してアルファを考慮した特殊な内部処理を
  行っているためで、RGBを塗りつぶした状態でRGBAのまま一括でresizeしてもその内部処理
  でフリンジが再発する。対策: RGB(3ch, "RGB"モード)とアルファ(1ch, "L"モード)を
  完全に別画像として個別に`resize()`し、最後に`Image.merge()`でRGBAに合成する。
  一括RGBA resizeを避けることで初めて解消する
- 「半透明ピクセルが無くなったこと」と「境界の色が均一であること」は別の検証項目。
  両方とも実際のピクセル値（`im.getpixel(...)`でアルファとRGBを境界付近で数値確認）
  で個別に確認する必要がある

## makeobj / dat 仕様

**画像制約**
- `makeobj pak128` は全画像の縦横サイズが **128の倍数** でないとエラー
- アイコン画像も 128×128 必須（48×48 等は不可）
- アイコン画像の左上(0,0)ピクセルが透過だとゲームが認識しない → 背景は不透過で塗りつぶす

**building dat の最小構成（駅拡張建物）**
```dat
obj=building
type=extension
waytype=track
enables_pax=1
NoInfo=1
Dims=1,1,4
cursor=icon.png.0.0
icon=icon.png.0.0
BackImage[0][0][0][0][0]=image.png.0.0
```

**building type 一覧（makeobj 60.11）**
| type | 説明 | 備考 |
|------|------|------|
| `extension` + `waytype=track` | 鉄道駅拡張建物 | ✓ ゲーム内表示確認済み |
| `stop` + `waytype=track` | 鉄道駅本体 | |
| `cur` | 観光地建物 | type指定のみでは表示されなかった（要調査） |
| `res`/`com`/`ind` | 市街地建物 | 自動生成 |
| `station`, `extension_building=1` | **obsolete** | 現 makeobj でビルドエラー |

**BackImage インデックス形式**
- 5形式 `[l][y][x][h][phase]` と 6形式 `[l][y][x][h][phase][season]` どちらも有効
- `seasons==1` の場合のみ 6→5 フォールバックあり
- image参照 `.row.col` は 128px グリッドの行/列インデックス（`row`→縦方向オフセット、`col`→横方向オフセット。`image_writer.cc:344` のコメント `[[[.row].col]` および行431 `block_getpix(x + col, y + row)` で確認）
- **書式は `ファイル名.行.列`（`.png` を含めない）が正しい。** makeobj (`image_writer.cc:372-388`) は画像参照文字列の最初の `.` より前だけを幹（ファイル名）として取り出し、`.png` を無条件に付与する。1つ目の数値は行番号、2つ目の数値は列番号として `atoi()` されるため、`"foo.png.4.3"` と書くと1つ目のトークン `"png.4.3"` は数値化できず行番号が0、2つ目のトークン `"4.3"` から列番号が4として扱われ、結果的に row=0, col=4（本来意図した row=4, col=3 ではない）として誤読される。row/col が両方0のときだけ `atoi("png.0.0")==0` が偶然一致し実害が出ない

**デバッグ**
- `makeobj VERBOSE DEBUG` で画像の読み込み詳細（座標・サイズ・オフセット）を確認できる
- makeobj はパラメーター不足・矛盾をほぼ無視して pak 生成する（エラーなし ≠ 正しい）

## vehicle dat 仕様（車両）

**画像キー（building の `BackImage` とは別書式）**
```dat
emptyimage[方向]=ファイル名.行.列
freightimage[方向]=ファイル名.行.列   # 積載状態がある場合
```
- `.png` は含めない（上記「BackImage インデックス形式」の注記を参照。row/col が0でない場合に literal に `.png` を挟むと誤動作する）
- 方向コード: `s, w, sw, se, n, e, ne, nw`（vehicle_writer.cc の `dir_codes` 配列順）
- 8方向揃えるか、対称車両なら4方向（s,w,sw,se）でも可（`vehicle_writer.cc` 参照）

**主要フィールド**
```dat
obj=vehicle
name=内部名
waytype=track          # 軌道種別
engine_type=electric   # diesel/electric/steam/...
speed=210               # km/h
power=11840              # kW
weight=81                # t
cost=3000                 # 購入価格(セント)
runningcost=30             # 走行コスト
maintenance=50              # 月額維持費
intro_year=1964
retire_year=2000
freight=Passagiere       # good名。pak128の旅客は"Passagiere"(独語)。"passenger"は存在せずFATAL ERROR
payload=56                 # 定員（capacityではなくpayload）
length=8                    # 車両長(1-24)
```
- `is_bidirectional` は makeobj 60.11 では未定義フィールド（警告のみ、無害）
- `freight` に存在しないgood名を指定すると `Cannot resolve 'GOOD-passenger'` のようなFATAL ERRORで
  ゲームが起動しない。pakset内の `symbol.<good名>.pak` ファイル名で正しいgood名を確認できる

**8方向の向き合わせはキャリブレーション方式が確実**
- カメラ角度・回転方向(CCW/CW)・ゲームエンジン内部のribi対応など、机上の三角関数だけで
  方向対応を導出するのは罠が多く、本プロジェクトでも2回外れた
- 確実な方法: 各方向レンダリングにZ回転角ラベル（例: `Z0`, `Z45`, ...）をPillow等で焼き込んだ
  キャリブレーション用dat（`emptyimage[方向]=対応するZ角度ラベル付き画像`の素直な1:1対応）を作り、
  実機で全方向（最低でも東西南北+斜め1つ）走らせてラベルを直読みする
- 0系新幹線の検証では「N/Sは素直なZ0/Z180で正しいが、E/W・NE/NW・SE/SWがペアで入れ替わる
  （東西軸の鏡映）」という規則性だった。Blenderモデル/カメラ側のX軸の向きの暗黙の仮定が
  ズレていたためと推測される（未特定）が、キャリブレーション方式なら原因究明不要で直せる

**vehicleの接地位置ズレ対策（makeobjの自動クロップ起因）**
- makeobjはPNGの非透過ピクセルからバウンディングボックスを自動検出してクロップする
  （`image_writer.cc` の `init_dim`）。8方向レンダーで回転ごとに可視シルエットの形が違うと
  クロップ位置・サイズがバラつき、ゲーム内で方向によって接地位置がズレて見えることがある
- 対策: 全レンダー画像の4隅（(0,0),(127,0),(0,127),(127,127)）に不透明1pxマーカーを焼き込み、
  強制的に128×128フルキャンバスでパックさせる。これでクロップ起因の差異を構造的に排除できる
- それでも均一なズレが残る場合は、カメラターゲットのZ座標を調整して画面内の表示位置を補正する。
  `px_shift = world_z_shift × 0.866 × (128 / ortho_scale)` の関係
  （0.866 = cos30°、Simutransの仰角30°由来）で必要なworld単位のオフセットを逆算できる

**流線型車両モデルは1枚のロフトメッシュで作る**
- 球(UV Sphere)をスケールするだけのノーズは断面が常に丸く、涙滴型・団子鼻にならない
- 円錐(直線テーパー)は逆に尖りすぎる（ピラミッド状）
- 車体・ノーズ・帯を別々のプリミティブ(直方体+球+直方体)で組むと、継ぎ目の「くびれ」や
  「□〇」の分離感、帯がテーパーに追従しない問題が起きやすい
- 確実な方法: bmeshでY軸方向に輪切りリングを並べて1枚のメッシュとしてロフトする。
  断面はスーパー楕円（角丸長方形、指数nが大きいほど箱っぽく・小さいほど丸くなる）、
  先端の半径は`tip_frac + (1-tip_frac) * sqrt(1-t²)`のようなカーブで減衰させると
  先端付近まで太さを保ちながら丸く収束する「団子鼻」形状になる。色帯はオブジェクトを
  分けずに、面の重心Z座標で`material_index`を出し分けることでテーパーに自動追従させられる

## dat linter（静的解析）

`try-out/dat_linter/`（Rust製PoC）で `obj=building` を対象に実装。
makeobjのソース（`building_writer.cc`/`get_waytype.cc`/`tabfile.cc`）を読むと
分かる「サイレントに失敗する」パターンが存在する:

- `cursor`と`icon`が両方とも空文字 → `cursorskin_writer_t`の呼び出し自体が
  スキップされ（`if (!c.empty() || !i.empty())`）、エラーなしでビルドメニューに表示されない
- タイル(`[layout][y][x]`)に`frontimage`/`backimage`が1枚もない →
  `phases=0`のままエラーなしで書き込まれ、そのタイルが空画像になる
- `frontimage`の高さ`h>0`は`dbg->error`止まり（fatalでない）→ 見逃されやすい
- `type=extension`で`waytype`未指定は「全waytypeに適合する汎用拡張」として
  正当に解釈される（仕様通りだが意図せずこうなりがち）

逆に`type`の不正値・obsolete keyword・`Dims`の`size=0`・`type=stop/depot`での
`waytype`欠落は makeobj 自身が`dbg->fatal`で止めるため非サイレントだが、
Blenderレンダリングを含むフルパイプラインを回さず一瞬で検出できる価値がある。

tabfileのキーは大文字小文字を区別しない（`tabfile.cc`の`format_key()`で
パース時に小文字化される）ため、dat内で`Dims`/`BackImage`のように
大文字を混ぜても問題ない。

画像サイズ「128の倍数必須」は`image_writer.cc`で確認済み:
`if ((width%img_size!=0)||(height%img_size!=0)) dbg->fatal(...,"Size not divisible by %d.")`
（`img_size`はpak128指定時128になる）。

**未確認ルール（要根拠調査）**: 「icon/cursor画像の左上(0,0)ピクセルが透過だと
ゲームが認識しない」という station_test 実験時の経験則は、`simutrans`サブモジュール
全体を検索しても該当ロジックが見つからなかった（makeobj側にもクライアント側にも
左上ピクセルを特別扱いする箇所がない）。当時の本当の原因が別だった可能性があり、
dat_linterの検証ルールからは一旦除外した。再現条件を切り分けてから復活させること。

**OTRP（Simutrans-Extended系フォーク, teamhimeh/simutrans）との関係**:
dat_linterの`KNOWN_TYPES`等の定数は本リポジトリの`simutrans`サブモジュール
（vanilla、コミット`1d2799f9a7`時点）からの書き写しであり、自動追従の仕組みはない。
OTRP（https://github.com/teamhimeh/simutrans, コミット`d6d3a5795b`時点、
2026-07-01に確認）の`building_writer.cc`/`get_waytype.cc`/`tabfile.cc`相当を
実際にcloneしてdiffした結果、**building dat の検証に関わるロジックは
vanillaと完全一致**だった（type/waytype一覧、cursor/icon省略時の挙動、タイル
画像欠落時の挙動、Dims size=0判定、画像サイズ128の倍数判定、キーの大文字小文字
非区別）。差分はnode書き込みのバイナリフォーマット詳細（バージョン番号・
write_uint16のオフセット指定方式など）のみで、dat記述者から見える挙動には影響しない。
そのため現状のdat_linterのルールはOTRP向けdatにもそのまま使える。
ただしOTRP独自のobjタイプ・フィールド（斜め線路駅設置など、
https://github.com/teamhimeh/simutrans/wiki/OTRP-Home 参照）には未対応。
本体・OTRPいずれかが更新されたら再diffが必要（自動追従の仕組みはまだない）。

## datフォーマッタとして安全にできること・できないこと

`tabfile_t::read()`（`tabfile.cc`）を精読した結果:
- **キーは`format_key()`で必ずトリム+小文字化されるので、キーの大文字小文字統一・
  `key = value`→`key=value`化（=前後の空白除去）は安全**
- **値は一切トリムされない**。`strchr(line,'=')`で分割した直後の文字列が
  そのまま`objinfo.put()`される。つまり`icon= foo.png.0.0`のように`=`の直後に
  スペースがあると、値は`" foo.png.0.0"`になり画像ファイル解決が
  サイレントに失敗する。dat_linterの`DatFile::parse`は当初これを`.trim()`で
  隠してしまっていたため、値を一切トリムしない実装に修正した（フォーマッタを
  作るために挙動を厳密に追い直したことでlinter自体のバグも見つかった）
- **値の内容（大文字小文字含む）は変更してはいけない**。`freight=Passagiere`等は
  実在するgood名と照合される。name/copyright/画像ファイル名も同様
- **行頭スペースで始まる行は`read_line()`の`*dest=='#' || *dest==' '`判定で
  丸ごと無視される**（コメット行と同じ扱い）。フォーマッタが勝手にスペースを
  除去して「有効化」すると意味が変わるため、原文のまま通し警告のみ出すべき
- **プロパティの記述順は`tabfileobj_t::objinfo`が`stringhashtable_tpl`
  （[tabfile.h:121](refs/simutrans/src/simutrans/dataobj/tabfile.h)）であるため
  makeobjの動作に一切影響しない**。「一般的な順序」は技術要件ではなく
  スタイルの慣習でしかなく、ソースから一意に導出することはできない
  （`building_writer.cc`内の`obj.get(...)`呼び出し順は参考にはなるが、
  実際の`station_cube.dat`の慣習と必ずしも一致しない）

`try-out/dat_linter/`の`dat_linter fmt`コマンドとして実装済み（デフォルトは
キー正規化のみで記述順維持、`--reorder`で並び替えはオプトイン）。

## linter / 静的解析の役割分担（formatter / linter / 静的解析の3層）

dat検証ツールを3層に分けて整理した:
- **formatter**: datを見やすく整形（意味は変えない）
- **linter**: makeobj（pak化ツール）自身の検証ルールに対する違反を検知
  （PHPで言う`php -l`に近い。パースできるか＝ビルドが通るかだけを見る）
- **静的解析**: ゲームエンジンのランタイムが前提とする不変条件への違反を検知
  （PHPで言うPHPStanに近い。実行しなくても「この条件で将来エラーになる」を予測する）

linterと静的解析はどちらも"静的"（ゲームを実行しない）だが、チェック対象の
権威が異なる。静的解析側は調査対象が`descriptor/writer/`ではなく
`vehicle/`等のランタイムコードになるため、調査コストも難易度も大きく異なる。
ただし「宣言されたデータだけで閉じる」問題（例: 連結制約の充足可能性）は
ランタイムコードを読まなくても解ける。一方「speed=0でクラッシュするか」のような
「ランタイム実装に依存する」問いは、別途ランタイムコードの調査が必要。

**車両連結制約の充足可能性（静的解析の最初のPoC）**: `vehicle_writer.cc`で
`constraint[prev][N]`/`constraint[next][N]`（直前/直後に連結可能な車両名の
リスト、`"none"`は先頭/末尾でよいという特別値）を確認。`xref_writer.cc`を見ると
makeobjは参照先車両名の実在性を検証しない（解決はゲーム読み込み時まで遅延）。
これを利用し、`try-out/dat_linter/`の`dat_linter couplings <dir>`で
START/END仮想ノードを使った到達可能性解析を実装。「自身を含む参照車両の
制約だけでは先頭〜末尾まで到達できない＝有限な編成が1つも組み立てられない
車両」を検出できる。車両名照合の大文字小文字区別は未検証（保守的に区別する
実装）。

## 自作ツール（サブモジュール）
| リポジトリ | 言語 | 役割 |
|---|---|---|
| simutrans-dat-parser | TypeScript | .dat 解析・書き込み |
| simutrans-image-util | TypeScript | 画像合成・透過・タイル分割 |
| simutrans-image-merger | Python | 画像レイヤー合成バッチ |
| simutrans（本体） | C++ | makeobj（dat+画像→pak） |
