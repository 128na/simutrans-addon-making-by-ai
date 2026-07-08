# t2i × isometric ControlNet PoC（観点1: モデリング参考画像生成）

作業日: 2026-07-08

## 目標

`try-out/t2i_research`（机上調査）で有望と判明した「Blenderレンダリングからdepth map/canny edgeを抽出し、
ControlNetの条件入力にしてt2iで理想形画像を生成する」手法を、実際にComfyUI上で動かして検証する。
具体的には以下を確認する。

1. ラフなBlenderレンダリング（箱＋切妻屋根）からcanny edge・簡易depth proxyを抽出できるか
2. SDXL + ControlNet(canny/depth) のworkflowをComfyUI API経由で構築・実行できるか
3. 生成画像がBlenderレンダリングと**同じ構図・同じアングル**を維持しつつ、建物らしいディテールを追加できるか
4. Blenderレンダリングとt2i生成画像を見比べて、VLM（Claude自身）が「モデルの作り込み不足」を言語化できるか

## 結果

**達成**。canny ControlNetによる構図一致は3パターンとも明確に成功し、VLMによる差分言語化（problem/solution形式）も実施できた。
depthは簡易プロキシでの検証にとどまり、本格的な効果検証は次回以降の課題として持ち越し。

## 試したこと

### 1. 入力画像の準備（Blenderレンダリング）

既存の `try-out/blender/isometric_box.py`（単純な箱のみ）だと形状情報が乏しく、canny edgeが
ほぼ立方体の輪郭線だけになってControlNetへの入力として弱いと判断し、新規に
[`building_render.py`](building_render.py) を作成した。箱＋切妻屋根（gable roof）の簡易建物形状とし、
カメラ設定はSimutrans標準（直交投影・俯角30°・方位45°、`CLAUDE.md`記載のBlenderパターンを踏襲）をそのまま使用。

- 出力: [`output/building_render.png`](output/building_render.png)（256×256 RGBA）
- 本物のZ-depth/Mistパスをコンポジタ経由で出そうとしたが、Blender 5.1で
  `scene.node_tree` → `scene.compositing_node_group` へのAPI変更、`CompositorNodeComposite`/
  `CompositorNodeOutputFile` の仕様変更に阻まれ、都度エラーが出た。深追いすると時間がかかるため
  **本格的な深度パス出力は見送り**、後述の簡易プロキシに切り替えた（コスト対効果判断）。

### 2. depth/canny抽出

[`preprocess_edges_depth.py`](preprocess_edges_depth.py)（OpenCV + Pillow使用、system Pythonに
`opencv-python-headless`を追加インストール）で以下を生成:

- **canny**: アルファ合成（白背景）→ グレースケール → `cv2.Canny(60, 150)` → SDXL生成解像度に合わせて1024×1024へニアレストネイバーでリサイズ
  → [`output/building_canny_1024.png`](output/building_canny_1024.png)
- **depth proxy**: 本格的なmonocular depth推定（ZoeDepth等）は今回のPoC規模には過剰と判断し見送り。
  代わりにアルファチャンネルのシルエットに `cv2.distanceTransform` を適用し、
  「シルエット中心に近いほど白（近い）・輪郭/背景に近いほど黒（遠い）」という**疑似的な立体感プロキシ**を生成
  → [`output/building_depth_proxy_1024.png`](output/building_depth_proxy_1024.png)
  - 注意: これは実カメラ距離に基づく真のdepthではなく、シルエット形状だけから作った近似値。
    「中心が最も近い」という前提は箱型の建物にはおおむね妥当だが、屋根の稜線のような凸形状の
    立体感は正しく表現できていない（後述の生成結果でも効果が限定的だった）。

### 3. ControlNet workflow構築（ComfyUI API Format JSON）

`try-out/t2i_research/comfyui_api_test.py` の `run_workflow()`/`load_workflow()`/`check_server_alive()`
をそのまま再利用し、新規に2つのworkflow JSONを手組みした。

- [`sdxl_controlnet_canny_api.json`](sdxl_controlnet_canny_api.json): SDXL base + `ControlNetLoader`
  (`controlnet-canny-sdxl-1.0.safetensors`) + `ControlNetApplyAdvanced`（strength=0.85, 全ステップ適用）
- [`sdxl_controlnet_canny_depth_api.json`](sdxl_controlnet_canny_depth_api.json): 上記に加えて
  depth ControlNet（`controlnet-depth-sdxl-1.0.safetensors`）を `ControlNetApplyAdvanced` で直列に追加
  （strength=0.35と弱めに設定。理由は上記のdepth proxy品質の低さを踏まえた保守的な選択）
- 生成解像度は1024×1024（SDXL標準）。DPM++ 2M Karras, 30 steps, CFG 7
- 制御画像はComfyUIの `input/` ディレクトリ（`E:\ComfyUI\input\`）に
  `t2i_iso_poc_canny.png` / `t2i_iso_poc_depth.png` としてコピーして`LoadImage`ノードから参照
- ランナースクリプト: [`run_controlnet_poc.py`](run_controlnet_poc.py)（3プロンプトパターンを一括実行）

事前にComfyUIサーバー疎通確認（`check_server_alive()`）を行い、既に起動済みだったためそのまま利用した
（VRAM free 2.6〜4.5GB程度で推移しており、他のPoC作業と並行利用されている様子だった。サーバー自体の
起動/停止は行っていない）。

### 4. 生成・目視確認

canny ControlNetのみで3プロンプトパターンを生成:

| pattern | seed | prompt概要 | 画像 |
|---|---|---|---|
| wooden_station | 42 | 木造駅舎、瓦屋根 | [output/t2i_iso_poc_canny_wooden_station_00001_.png](output/t2i_iso_poc_canny_wooden_station_00001_.png) |
| brick_cottage | 123 | レンガ造コテージ、テラコッタ瓦屋根 | [output/t2i_iso_poc_canny_brick_cottage_00001_.png](output/t2i_iso_poc_canny_brick_cottage_00001_.png) |
| stone_shrine | 777 | 石造の日本の祠、木の梁 | [output/t2i_iso_poc_canny_stone_shrine_00001_.png](output/t2i_iso_poc_canny_stone_shrine_00001_.png) |

canny+depth（strength弱め）の追加検証（wooden_stationと同一プロンプト・同一seed）:

- [output/t2i_iso_poc_canny_depth_00001_.png](output/t2i_iso_poc_canny_depth_00001_.png)

## 得られた知見や失敗

### 構図一致: 成功

3パターンとも、入力Blenderレンダリング（箱＋切妻屋根、俯角30°・方位45°）と**同一の直方体プロポーション・
同一の屋根の稜線方向・同一のカメラアングル**を維持したまま生成できた。プロンプトを大きく変えて
「木造駅舎」「レンガコテージ」「石造の祠」という全く異なる建物ジャンルを指定しても、canny edgeが
シルエット・稜線の位置を強く拘束しており、構図のブレは目視で確認できなかった。事前調査の
「角度制御=ControlNet」という定石を実機で裏付けられた。

### depth proxy: 効果は限定的

distance transformベースの簡易depthを弱いstrength(0.35)で追加しても、canny単体の結果と比べて
劇的な変化は見られなかった（同一プロンプト・同一seedの比較: wooden_station vs canny_depth）。
むしろ壁面と屋根面の質感差がやや薄まり、画像全体が均質な木目調になる傾向が見えた。これは
depth proxyが「シルエット中心が近い」という単純な仮定に基づいており、実際の面ごとの傾き・距離を
表現できていないためと考えられる。**depth ControlNetを本格的に活用するには、Blenderの実Z-depthパス
出力（今回は5.1のAPI変更で見送った）か、既存のmonocular depth推定モデル（ZoeDepth等）の導入が必要**、
という次回への課題が明確になった。

### VLM差分検出（problem/solution形式）

Blenderレンダリング（[building_render.png](output/building_render.png)、単色フラットシェーディングの
箱＋切妻屋根）と、canny ControlNet生成画像（[wooden_station](output/t2i_iso_poc_canny_wooden_station_00001_.png)）
を見比べ、Claude自身がVLMとして「Blenderモデルの作り込み不足」を3点言語化した。

1. **problem**: 屋根が厚みゼロの単純な三角平面2枚で、瓦・棟包み・軒の出（オーバーハング）が一切ない。
   生成画像では瓦の重なりと軒先が壁面より外側に張り出しているのに対し、元モデルは壁と面一（ツライチ）の
   単純なランプ形状になっている。
   **solution**: 屋根メッシュに厚み（Solidify）を持たせ、壁面より僅かに外側へ張り出させる。可能であれば
   瓦の凹凸をノーマルマップまたはジオメトリで追加する。
2. **problem**: 壁面が単色フラットマテリアルのみで、板張り・レンガ等の質感情報が皆無。
   生成画像は縦板張り（wooden_station）やレンガ目地（brick_cottage）の細かいディテールを描き込んでいる。
   **solution**: 壁面マテリアルに板張り/レンガのプロシージャルテクスチャまたは画像テクスチャを追加し、
   最低限ノーマルマップで凹凸感を出す。
3. **problem**: 建物が透過背景に直接浮いており、接地面の処理（基礎・土台、周辺の地面装飾）が無い。
   生成画像は建物の下にわずかな段差や芝生の土台があり、Simutransの1タイル上に自然に載っているように
   見える。元モデルは単なる影のみで「浮いている」印象が強い。
   **solution**: 建物本体の下に薄い基礎ブロック（タイル境界に合わせたfootprint）を追加し、視覚的な
   接地感を持たせる（これは観点2のtry-outで検討している「周辺タイル装飾」とも関連する）。

この結果は事前調査で参照したLL3M（複数視点レンダリング→VLM批評→problem/solution形式フィードバック→
3D修正）の枠組みがそのまま今回のtry-outでも機能することを示しており、次段階として
「t2i生成画像を参照しつつBlenderスクリプトを自動修正するループ」の実装可能性が具体的に見えてきた。

### その他ハマった点

- **Blender 5.1のコンポジタAPI変更**: `scene.node_tree`が廃止され`scene.compositing_node_group`に
  変わっていた。`CompositorNodeComposite`ノードも存在せず（新しいノードグループ仕様に未対応）、
  `CompositorNodeOutputFile`も`base_path`属性が無いエラーで失敗した。深追いを避けdepth pass出力は
  断念し、PIL/OpenCVによる後処理プロキシに切り替えた判断は妥当だった（本来のdepth推定精度は
  犠牲にしたが、PoCとしての構図一致検証という主目的には影響しなかった）
- **system PythonにOpenCV未導入**: system Python(3.14.3)にもComfyUIのvenvにも`cv2`が無かったため
  `pip install opencv-python-headless`で追加導入した（ComfyUI venv側は変更していない）
- **VRAM逼迫**: `check_server_alive()`で見たVRAM freeが2.6〜4.5GB程度と少なく、他のPoC作業
  （観点2のinpainting検証、ComfyUI `input/`に`t2ipoc_canvas.png`等が存在していたことから推測）と
  並行利用されていた模様。今回は1024×1024 SDXL + ControlNet 1〜2本の生成が問題なく完走したため
  実害はなかったが、並行作業が増えるとOOMのリスクがある点は留意事項として残しておく

## 次回への引き継ぎ

- depth ControlNetを本格活用するなら、Blender 5.1のコンポジタ新API（`compositing_node_group`）を
  正しく使ったZ-depth出力方法を先に確立するか、ZoeDepth等の軽量monocular depth推定モデルを導入する
- 今回はVLM差分検出を「言語化するところまで」で止めたが、次はこの3点をBlenderスクリプト側の
  修正（Solidify追加・テクスチャ追加・基礎ブロック追加）に反映し、render-compare-refineループの
  1サイクル目を実際に回してみる
- 観点2（inpaintingによる周辺装飾）のPoCとも接点がある（今回の「接地感が無い」指摘は観点2の
  「周辺装飾で解決すべき課題」と本質的に同じ）。両方のtry-outの知見を統合すると効率が良さそう

## フィードバック対応（2026-07-08）

ユーザーが生成結果を確認し、「形状としては狙ったものにできていそう。気になる点は影は不要、
ベースタイルの形状とぴったり一致できないか」というフィードバックを受け、以下2点に対応した。
ComfyUIサーバーは前回セッション終了後に停止していたため、`check_server_alive()`で確認のうえ
自分で再起動している（他PoC作業との共用を想定し、再起動後もプロセスは維持したまま）。

### 1. 影（cast shadow）の除去

**結果: プロンプト側での抑制は部分的成功（3パターン中1〜2パターン）、後処理フォールバックで安定的に除去できることを確認**

- まずnegative promptに`shadow, cast shadow, drop shadow, ambient occlusion`等、positive promptに
  `flat lighting, no shadow, clean silhouette, no ground, no floor`等を追加して再生成した
  （[`sdxl_controlnet_canny_api.json`](sdxl_controlnet_canny_api.json)を更新、
  [`run_controlnet_poc.py`](run_controlnet_poc.py)のプロンプトも同様に更新）。
  - brick_cottage・stone_shrineの2パターンは影がほぼ消えた
    （[brick_cottage_noshadow](output/t2i_iso_poc_canny_brick_cottage_noshadow_00001_.png)、
    [stone_shrine_noshadow](output/t2i_iso_poc_canny_stone_shrine_noshadow_00001_.png)）
  - wooden_stationパターンは強い落ち影が残存し、プロンプト強調構文（`(no shadow:1.4)`等）を
    使った再試行（[v2](output/t2i_iso_poc_canny_wooden_station_noshadow_v2_00001_.png)）でも
    改善しなかった。SDXLが「写実的なisometricオブジェクトレンダリング」というスタイルに
    落ち影を強く紐付けて学習している可能性が高く、プロンプトだけでは完全な抑制は不安定と判断
- フォールバックとして後処理での影除去を実装（[`postprocess_remove_shadow.py`](postprocess_remove_shadow.py)）。
  背景がほぼ均一なフラットカラーで、影はその背景色の**明度だけを落とした同系色ブロブ**として
  現れるという今回観察された共通パターンを利用し、HSV空間で背景と色相(Hue)・彩度(Saturation)が
  近い画素を「背景 or 影」とみなして透過化する（明度Valueの差は無視）。さらに最大連結成分のみを
  残すことで孤立ノイズを除去した
  - 最も影が強く残ったwooden_station_noshadow_v2に適用した結果、影・背景とも完全に透過化できた
    （[`t2i_iso_poc_canny_wooden_station_noshadow_v2_shadowremoved.png`](output/t2i_iso_poc_canny_wooden_station_noshadow_v2_shadowremoved.png)、
    チェッカーボード合成での確認用: 建物本体のみが残り影の痕跡は見られない）
  - 他3パターンにも同様に適用し、いずれも影・背景を透過化できることを確認した
    （`*_shadowremoved.png`一式）
  - **知見**: 影抑制は「プロンプト調整で狙う→ダメなら後処理で確実に除去する」の2段構えが
    実用的。プロンプトだけに頼ると再現性が不安定なため、pak化パイプラインに組み込む場合は
    後処理ステップを標準搭載しておくのが無難

### 2. 生成結果の接地面（footprint）をベースタイル菱形に整合させる

**結果: 診断→原因特定→カメラキャリブレーション修正により、ほぼ完全に一致させることに成功**

- まず`try-out/t2i_inpaint_poc/crop.png`（128×128、透明=タイル菱形・青=タイル外）を分析し、
  「菱形は画像**全幅**を使い、高さ=幅/2、**画像下端に接地**」という座標定義を特定した
  ([`overlay_tile_diamond.py`](overlay_tile_diamond.py)の`diamond_points()`に実装)
- この菱形を旧生成画像（[wooden_station_noshadow](output/t2i_iso_poc_canny_wooden_station_noshadow_00001__shadowremoved.png)）に
  重ねると（[`BEFORE_diamond_overlay_wooden_station.png`](output/BEFORE_diamond_overlay_wooden_station.png)）、
  建物の接地面が菱形の下端頂点より**205px**（1024px中約20%）も上に浮いており、菱形の横幅に対して
  建物が小さく中央寄りに描かれていることが判明した
- **原因**: `building_render.py`のBlenderカメラが`ortho_scale=2.4`（屋根を画角に収めるための
  場当たり的な値）を使っており、`try-out/blender/isometric_box.py`・CLAUDE.md記載の
  「1×1 BUタイル→画角ぴったり」という標準キャリブレーション（`ortho_scale=sqrt(2)`）から
  外れていたことが根本原因と特定した
- **診断・修正**: [`diag_tile_marker.py`](diag_tile_marker.py)を新規作成し、建物本体の代わりに
  「原点中心の1×1 BU地面タイル（マゼンタ平面, z=0）」だけを同じカメラ設定でレンダリングして
  実測することで、キャリブレーションのズレを定量的に確認しながら補正値を特定した:
  1. `ortho_scale=sqrt(2)`に戻すと、タイル菱形が画像**全幅**を使うようになった（横方向は解決）
  2. しかし屋根を収めるため`resolution_y`を`resolution_x`より大きくする（256×384）と、
     Blenderのセンサーフィット既定動作(`AUTO`)が縦基準に切り替わり横幅の較正が崩れるため、
     `sensor_fit='HORIZONTAL'`を明示指定して横幅基準のスケールを固定した
  3. さらに縦に拡張した分だけタイルが画面中央に浮いてしまう（上下に均等に余白が付加される）
     ため、`camera.data.shift_y=0.25`でフレーミングをオフセットし、**タイル菱形が常に
     キャンバス最下端に接地し、拡張した余白がすべて屋根用のヘッドルームとして上側に来る**
     ように補正した（値はマーカーレンダリングで実測しながら符号・大きさを特定）
  4. 補正後の設定（`ortho_scale=sqrt(2)`, `sensor_fit='HORIZONTAL'`, `shift_y=0.25`,
     解像度256×384）で[`building_render.py`](building_render.py)を更新・再レンダリングし、
     [`diag_tile_marker.py`](diag_tile_marker.py)でも同設定を反映して再検証、菱形が
     画像全幅・最下端接地になることを確認した
- 補正後のBlenderレンダリング（[`output/building_render.png`](output/building_render.png)、256×384）に
  菱形を重ねると（[`building_render_diamond_overlay.png`](output/building_render_diamond_overlay.png)）、
  建物の手前下端の角が菱形の手前頂点にほぼ一致した
- canny/depthを新しいレンダリングから再抽出（[`preprocess_edges_depth.py`](preprocess_edges_depth.py)を
  非正方形キャンバス対応に更新、`building_canny_gen.png`等を832×1248で新規出力。832×1248は
  256×384のアスペクト比(2:3)を厳密に保ったSDXL互換解像度）し、新規ワークフロー
  [`sdxl_controlnet_canny_tilealigned_api.json`](sdxl_controlnet_canny_tilealigned_api.json)
  （EmptyLatentImageを832×1248に変更）で再生成した
  （[`t2i_iso_poc_canny_tilealigned_00001_.png`](output/t2i_iso_poc_canny_tilealigned_00001_.png)、
  影除去後: [`t2i_iso_poc_canny_tilealigned_00001__shadowremoved.png`](output/t2i_iso_poc_canny_tilealigned_00001__shadowremoved.png)）
- 生成結果に菱形を重ねて確認した（[`tilealigned_diamond_overlay_final.png`](output/tilealigned_diamond_overlay_final.png)）ところ、
  建物本体の接地面が菱形の3頂点（手前・左・右）にほぼ正確に一致した。ピクセル単位で定量確認した結果:
  - 建物の不透明画素の最下端行 = **y=1247**（キャンバス最下端 = 1247、**誤差0px**。
    修正前は最下端行=818でキャンバス最下端1023との差が205pxあった）
  - 最下端行でのx範囲は399-426（中心≈412.5）、期待される菱形手前頂点のx=416と**誤差4px程度**
  - 左端は x=0（キャンバス左端）にy=1036-1041で接触、期待される菱形左頂点(0, 1039)と**誤差2px程度**
  - 右端は x=831（キャンバス右端）にy=1039を含む範囲で接触、期待される菱形右頂点(831, 1039)と**誤差0px程度**
  - → **接地面の3頂点すべてが数px単位で菱形頂点と一致**しており、「ぴったり一致」の目標は
    ほぼ達成できたと判断できる
- **副作用として判明した知見**: 屋根を収めるために縦方向のキャンバスを拡張した結果、
  canny画像の建物本体より上側に大きな余白（エッジ情報の無い領域）ができ、SDXLがその余白に
  「本来の3倍近い大きさの屋根」「用途不明な2本の柱状オブジェクト」を自由に描き足してしまう
  現象が起きた（[`t2i_iso_poc_canny_tilealigned_00001_.png`](output/t2i_iso_poc_canny_tilealigned_00001_.png)参照）。
  これはControlNet(canny)が「エッジが存在する場所」しか拘束できず、余白領域には拘束が
  働かないために起きる、ある意味当然の挙動。**接地面（タイル整合）の精度には影響しなかったが**、
  実運用でこの手法を使う場合は、(a)入力のBlenderモデル自体をある程度高さのあるものにして
  余白を減らす、(b)キャンバス上部にも簡単なガイド用エッジ（雲・空の境界線等）を入れて
  拘束を与える、(c)strengthをさらに上げる、等の対策が次の課題として残る
- 影除去の後処理は、この菱形整合済み生成画像に対しても問題なく機能した
  （床面の淡いグレー要素がやや残存したが、これは影というより「floor」オブジェクトを
  negative promptで抑制しきれなかったケースで、影除去ヒューリスティックの対象外だった。
  影そのものの除去は成功している）

### まとめ

| 項目 | 対応前 | 対応後 |
|---|---|---|
| 影 | 3パターン中1〜2で強い落ち影 | プロンプト調整＋後処理フォールバックで全パターン除去確認 |
| 接地面とタイル菱形の一致 | 最大205px（約20%）のズレ、菱形が建物より大きく浮く | 頂点誤差0〜4px、ほぼ完全一致 |

接地面のズレは「t2i側の生成の不安定さ」ではなく「**入力Blenderレンダリング自体のカメラ
キャリブレーションが標準タイル定義とズレていた**」ことが根本原因であり、Blender側を
修正するだけでControlNet(canny)が高精度に追従したという点が今回の重要な発見。
ControlNetの構図拘束力の高さ（前セクションで確認済み）が、そのままタイル整合の精度にも
活かせることが実証できた。
