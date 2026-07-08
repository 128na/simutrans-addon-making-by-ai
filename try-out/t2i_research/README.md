# text-to-image (t2i) 活用可能性の調査

作業日: 2026-07-08

## 目標
今後の3Dモデル作成・レンダリング後処理にtext-to-image (t2i) を活用できないか、実装前の技術調査を行う。
- 観点1: 3Dモデルをスクラッチ作成する際の見本として（0系新幹線作成時の「参考にできる完成形の絵がない」課題への対応）。
  t2iで参考画像を生成し、Blenderレンダリングとの差分＝作り込み不足箇所として検出、自律的にモデリングを進められないか
- 観点2: 建物レンダリング時のベースタイル作成として（PLATEAU由来の建物レンダリングに周囲の歩道・植生がない課題への対応）。
  レンダリング後の建物画像に、建物本体を壊さず周辺だけ装飾を合成できないか
- 観点3: 上記を実現するt2i環境構築（ローカル vs API、Windows対応、コスト、ライセンス）

当初は3件の並列Web調査（サブエージェント）による机上調査のみを想定していたが、その後ローカルComfyUI環境構築・観点1/観点2それぞれのPoCまで実施した（本ディレクトリの「ComfyUI環境構築」節、および [try-out/t2i_isometric_poc/](../t2i_isometric_poc/README.md)・[try-out/t2i_inpaint_poc/](../t2i_inpaint_poc/README.md)を参照）。

## 結果
達成（机上調査・環境構築・観点1/観点2の両PoCまで完了。isometric視点特有の破綻など次フェーズの課題も具体化できた）

## PoC実施結果サマリー（2026-07-08）

- **環境構築**: ComfyUI（ローカル、`E:\ComfyUI`）+ SDXL base/inpainting + ControlNet(canny/depth) の構成で、Pythonから`/prompt` API経由のheadless実行が確立できた。ダウンロード未完了のまま報告されるトラブルがあったが、Main側のtrust-but-verifyで検出・解消（詳細は下記「ComfyUI環境構築」節）
- **観点1（[t2i_isometric_poc](../t2i_isometric_poc/README.md)）**: canny ControlNetによるisometric構図一致は**成功**。簡易Blenderレンダリング（箱+切妻屋根）と同一の構図・カメラアングルを保ったまま、木造駅舎/レンガコテージ/石造祠の3パターンでディテールを追加した画像を生成できた。VLM（生成エージェント自身）による差分の言語化も実施し「屋根の厚み/壁面テクスチャ/接地感」の3点を欠落箇所として抽出できた。depth ControlNetは簡易プロキシでは効果が限定的で、本格活用には実Z-depth出力（Blenderコンポジタ）かZoeDepth等の導入が必要
- **観点2（[t2i_inpaint_poc](../t2i_inpaint_poc/README.md)）**: 建物保護は**成功**（不透明ピクセルの99.4%が後処理後も完全一致）。一方isometric視点の自然さは**やや破綻**（事前調査の懸念通り、周辺の植栽・地面が「平面的に浮いて見える」）。タイル境界整合は今回はたまたま目立たなかったが、シームレス設計はできておらず未解決の課題として残る。256×256ネイティブ生成は完全崩壊するため1024×1024生成→ダウンスケールの2段構成が必要という実装上の知見も得られた

## 試したこと
観点ごとに独立したリサーチエージェントを並列実行し、Web調査を行った。

- 観点1: isometric角度の安定化手法、レンダリングとt2i画像の差分検出手法、自律的なrender-compare-refineループの先行事例を調査
- 観点2: 透過PNG（建物のみ）へのinpainting/outpaintingによる周辺装飾手法、建物保護の制御方法、isometric視点特有の懸念、タイル境界整合を調査
- 観点3: ローカル実行（ComfyUI/Automatic1111/Fooocus）とAPI（Stability AI/OpenAI/Google Imagen/Midjourney）の比較、Windows対応・VRAM要件・自動化のしやすさ・ライセンスを調査

## 得られた知見や失敗

### 観点1: モデリング見本としてのt2i（render-compare-refineループ）

- **プロンプトのみでのisometric角度再現は不安定**という既存認識（knowledge.md記載）は調査でも裏付けられた。角度を厳密に固定するには、**Blenderレンダリング（またはラフな箱組みモデル）からdepth map/canny edgeを抽出し、ControlNetの条件入力にしてt2iを行う**手法が実用解として複数ソースで一致していた。IP-Adapterは画風統一には効くが角度制御には弱く、「角度制御=ControlNet、画風統一=IP-Adapter」と役割分担するのが定石
- **差分検出はSSIM/CLIP embeddingのような数値指標より、VLM（GPT-4V/Gemini/Claude等）に2枚の画像を渡して自然言語で差分を言語化させる方が実用的**。CLIP embeddingは意味的に異なる画像を高い類似度で誤って一致させる問題（"erroneous agreement"）が指摘されている
- 想定していた「t2iで理想画像を作る→VLMで差分言語化→3D修正」という3段構えの自律ループに極めて近い先行研究として **LL3M**（Blenderを駆動する3D生成エージェント。5視点レンダリング→VLM批評→"problem/solution"形式のフィードバック→既存Blenderスクリプトの部分修正）と **SceneCraft**（レンダリング画像とテキスト記述の整合をGPT-Vで評価し自己修正する二重ループ）が見つかった。ただしどちらも**t2iで理想画像を経由せず、VLMが直接レンダリング画像を批評する2段構成**が主流で、t2i理想画像を挟む構成（このプロジェクトの想定）は「t2i画像→3D差分」の変換にひと手間かかる点に注意
- DreamFusion（Score Distillation Sampling）は「t2iモデルの知識を3D生成の修正信号に使う」という発想の数学的な原型として参考になるが、離散的なVLM批評ではなく連続的な勾配降下による最適化であり、直接の実装参考にはなりにくい

### 観点2: ベースタイル装飾としてのt2i（inpainting/outpainting）

- 建物本体を壊さず周辺だけ生成するワークフローは確立されている: **アルファチャンネルを反転してinpaintマスクに使う → ControlNet（Depth/Canny）で建物のシルエット情報を条件付けする → 生成後に元の建物レイヤーを最上位に貼り戻して建物ピクセルを完全に保護する**、という多段階の組み合わせが実用パターン。最も近い先行事例は自動車の透過PNGを対象にした[Outpainting III - Inpaint Model (HuggingFace Blog)](https://huggingface.co/blog/OzzyGT/outpainting-inpaint-model)
- 本プロジェクトは既にBlender側でRGBA背景透過PNGを持っているため、一般的なworkflowで最初に必要な「背景除去ステップ」が不要という点で有利なスタート地点
- **isometric視点での周辺生成は確立手法が見当たらない未検証領域**。一般のt2i/ControlNetは真俯瞰・正面視点に強くisometricは弱点という指摘が複数あり、「歩道の遠近感・タイルの向きが建物の投影角と一致せず浮いて見える」破綻が想定される最大のリスク。ただし今回は「isometricをゼロから生成する」のではなく「既にisometricで正しい建物の周辺だけ」を生成するため、Depth ControlNetの陰影方向の一貫性＋強めのプロンプト誘導で緩和できる可能性がある（未検証）
- **128px単位タイル境界との整合も先行事例なし**。汎用の"seamlessテクスチャ"手法は水平無限リピート用でオブジェクト指向の今回のケースとは性質が異なる。「1タイルごとに独立生成せず、複数タイル分をまとめた大きなキャンバスで一括outpaintしてから後でタイル境界にカットする」という対応方針の仮説はあるが未検証

### 観点3: t2i環境構築

- **ComfyUIを推奨**。ノードベースでControlNet/img2img/inpainting/outpaintingを標準〜準標準サポートし、workflow JSONを`/prompt`エンドポイントにPOSTすることでBlenderヘッドレスパイプラインと同様に**Pythonから完全headless自動化できる**。VRAM効率もAutomatic1111よりよい（SDXLで約14%省VRAM）
- Automatic1111は`--api`フラグでREST API化できるがノード単位の細かい制御はComfyUIに劣る。Fooocusは省VRAム・簡単導入が売りだが細粒度カスタムワークフローに不向きで、今回の用途（ControlNet併用の差分比較支援・inpaint装飾）には力不足の可能性が高い
- API（Stability AI/OpenAI/Google Imagen）はローカルGPU不要で$0.02〜0.08/枚程度。ただしControlNet相当の構造制御が弱いか、APIが用意した機能セットに限定される。Midjourneyは公式APIがEnterprise限定のため対象外
- **ライセンス注意点**: FLUX.1 [dev]は非商用ライセンスのみ（商用利用には別途有料ライセンスが必要）。商用利用したい場合はFLUX.1 [schnell]（Apache 2.0）かSDXL（CreativeML Open RAIL-M）を選ぶ。PLATEAUデータ（CC BY 4.0）とt2iモデルのライセンスは直接抵触しないと考えられるが、**PLATEAU側の帰属表示義務はt2i生成物を組み込んだ最終アドオンにも引き続き適用される**点に注意（一般的な解釈であり、広く配布する段階では法務確認を推奨）

## 次回への引き継ぎ（次の一手）

観点1・観点2は独立して検証できるため、それぞれ別のtry-outディレクトリで進める想定。

1. **環境構築（前提）**: ComfyUIをローカルにインストールし、workflow JSON経由でPythonからheadless実行できることを最初に確認する（既存Blenderパイプラインと同様の「スクリプトから叩ける」形が成立するかが自動化の前提条件）。モデルはライセンスが明快なSDXLまたはFLUX.1 schnellを採用し、FLUX.1 devは避けるかREADMEに非商用限定と明記する
2. **観点1のPoC**: 既存Blenderレンダリングからdepth map/canny edgeを抽出 → depth ControlNet + 建物系プロンプトで同一構図のisometric風画像を生成 → 構図が一致するか目視確認 → 一致すればBlenderレンダリングとControlNet生成画像の2枚をVLM(Claude等)に渡し「作り込みが足りない箇所を3点挙げて」と自然言語で差分を出させてみる
3. **観点2のPoC**: 単一タイル(128×128)の建物透過PNG1枚を用意 → キャンバスを256×256程度に拡張しinpaintマスク設定 → Depth ControlNet（Blenderレンダリング時にZ-depthも同時出力）+ isometric視点を強く誘導するプロンプトで周辺生成 → 元の建物レイヤーを貼り戻して保護 → (a)建物エッジの侵食有無 (b)歩道・植栽の消失点/影の向きが建物のisometric角度と揃っているか (c)複数回生成時の一貫性 (d)隣接タイルに敷き詰めた際の継ぎ目破綻、を評価
4. GPU投資が難しい場合は、上記2つの最小構成をAPI版（Google Imagen Fast等）でも組めるか比較し、ローカルGPU投資とAPI従量課金の損益分岐点を試算する

## ComfyUI環境構築（2026-07-08 実施）

上記「次の一手」1.を実施し、ローカルComfyUI環境の構築とheadless API疎通確認まで完了した。

### インストール内容
- 設置場所: **リポジトリ外 `E:\ComfyUI`**（他プロジェクトでも使い回す汎用ツールのため、モデル込みでリポジトリのgit管理・作業ディレクトリ配下には置かない方針）
- ComfyUI本体（公式リポジトリ）をclone、`E:\ComfyUI\venv`にPython venvを作成しpip install（torch 2.11.0+cu128、CUDA利用可能・RTX 4070 Ti認識を確認済み）
- 導入モデル（いずれもHugging Face公式配布元から取得、ライセンス明快なもののみ採用）:
  - `sd_xl_base_1.0.safetensors`（SDXL base 1.0、CreativeML Open RAIL-M、約6.94GB）
  - `sd_xl_base_1.0_inpainting_0.1.safetensors`（SDXL inpainting、約6.94GB、観点2 PoCで使用予定）
  - `controlnet-canny-sdxl-1.0.safetensors` / `controlnet-depth-sdxl-1.0.safetensors`（各約2.5GB、観点1/観点2 PoCで使用予定）
- 起動コマンド: `E:\ComfyUI\venv\Scripts\python.exe E:\ComfyUI\main.py` → `http://127.0.0.1:8188`

### API疎通確認
- [comfyui_api_test.py](comfyui_api_test.py) を整備。`/prompt`にworkflow JSON（[sdxl_txt2img_api.json](sdxl_txt2img_api.json)）をPOSTし、`/history`をポーリングして完了を待ち、`/view`から画像を取得する最小ヘルパー（`queue_prompt`/`wait_for_completion`/`fetch_image`/`run_workflow`）を実装。観点1/観点2のPoCでもそのまま再利用する
- 実行結果: **成功**。`python comfyui_api_test.py`でSDXL base単体のtxt2img（"a simple wooden train station building, isometric view, clean background"）が完走し、`output/`に画像を保存できることを確認した

### ハマった点
- **ダウンロード未完了のまま作業を終えてしまった問題**: 環境構築を担当したサブエージェントが、モデルファイルのバックグラウンドダウンロード（`curl`）が完了する前に作業を終了し、「ダウンロード監視の仕組みを用意したので待つ」という趣旨の报告で完了通知が上がってきた。Main側で`git status`ならぬファイルサイズ直接確認（trust-but-verify）を行ったところ、`sd_xl_base_1.0.safetensors`が公式サイズ6.94GBに対し実測3.99GB（後の再確認では4.7GB、つまり実測中も動的に増加していた）しかなく、ダウンロードが継続中であることが判明した。この状態で`comfyui_api_test.py`を実行すると`CheckpointLoaderSimple`ノードで`shape '[10240, 1280]' is invalid for input of size 6932161`という safetensors 読み込みエラーで失敗した（ファイルが途中までしか書き込まれていないことによる破損）
  - 対応: サブエージェントの報告を鵜呑みにせず、ファイルサイズ・実行プロセス（`tasklist`で`curl.exe`が2本稼働中と判明）を直接確認 → 既存のダウンロードプロセスの完了を待機（`until`ループ＋バックグラウンドBash） → 完了後（両ファイルとも6.94GBに到達）に再実行し成功を確認、という流れで解決した
  - 教訓: 「モデルダウンロードのような時間のかかる作業を含むタスクをサブエージェントに委譲した場合、完了報告の文面だけでなく、実ファイルのサイズ・稼働プロセスを直接確認してから次工程に進むべき」という`trust-but-verify`の重要性を再確認した事例
