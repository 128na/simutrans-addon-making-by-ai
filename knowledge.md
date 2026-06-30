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
- image参照 `.x.y` は 128px グリッドのコラム/行インデックス（`.png` 拡張子あり・なし両方可）

**デバッグ**
- `makeobj VERBOSE DEBUG` で画像の読み込み詳細（座標・サイズ・オフセット）を確認できる
- makeobj はパラメーター不足・矛盾をほぼ無視して pak 生成する（エラーなし ≠ 正しい）

## vehicle dat 仕様（車両）

**画像キー（building の `BackImage` とは別書式）**
```dat
emptyimage[方向]=ファイル名.png.列.行
freightimage[方向]=ファイル名.png.列.行   # 積載状態がある場合
```
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

## 自作ツール（サブモジュール）
| リポジトリ | 言語 | 役割 |
|---|---|---|
| simutrans-dat-parser | TypeScript | .dat 解析・書き込み |
| simutrans-image-util | TypeScript | 画像合成・透過・タイル分割 |
| simutrans-image-merger | Python | 画像レイヤー合成バッチ |
| simutrans（本体） | C++ | makeobj（dat+画像→pak） |
