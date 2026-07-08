# t2i inpaintingで装飾したPLATEAU建物のアドオン化（最終パイプライン化）

作業日: 2026-07-09

## 目標

`try-out/t2i_inpaint_poc`で作成した「SDXL inpaintingで建物周辺に花壇等を生成した装飾済み画像」を、
実際にSimutransでゲーム内表示できるアドオン（.dat + .pak）に落とし込む。t2i_inpaint_poc自体は
画像生成PoCとしては完結していたが、生成物をpak化してゲーム内アセットとして成立させる工程は
未着手だったため、その最後の一歩を検証する。

## 結果

**達成**。dat_linter・makeobjともにエラーなく完走し、ゲーム内表示もユーザーより「表示OK」と確認済み。

## 試したこと

### 1. 候補画像の選定

`try-out/t2i_inpaint_poc/output/final_t2ipoc_*`のうち、README記載の評価が最も高かった
[`final_t2ipoc_v5g_cn025_seed123_00001_.png`](../t2i_inpaint_poc/output/final_t2ipoc_v5g_cn025_seed123_00001_.png)
（アプローチ2＝ControlNetガイド線+段階的denoiseマスク、seed123）を採用した。README曰く
「今回のPoC全体を通じて最も良好な結果。紫〜ピンクの花が建物の可視左辺全体に連続的に並び、
建物の壁面から途切れなく生えているように見える」とあり、実際に目視でも同シリーズ内で
最も花が建物に沿って連続的に配置されていることを確認した（[`final_t2ipoc_v5_full_seed123_00001_.png`](../t2i_inpaint_poc/output/final_t2ipoc_v5_full_seed123_00001_.png)
と見比べても、花の密度・建物との接続感でv5gの方が優れていた）。

### 2. 画像サイズ問題への対処: 256×256 → 128×128へダウンスケール

候補画像は256×256 RGBAだが、pak128の`BackImage`は本来128×128が標準（`plateau_building.dat`も
128×128）。`try-out/t2i_inpaint_poc/postprocess_v5.py`のソースを確認したところ、この256×256は
「128×128キャンバスを`FINAL_SCALE=2`で単純に2倍拡大しただけ」（`building_resized =
building.resize((256,256))`、キャンバス全体を埋める2倍ズームであって、周囲に余白を追加した
ものではない）と判明した。

この事実を踏まえ、**256×256のまま`BackImage`に使うのではなく、128×128へダウンスケールする**
判断をした。理由:

- `refs/simutrans/src/simutrans/descriptor/writer/image_writer.cc`の`write_obj()`を確認すると、
  `image.x`/`image.y`（画像の描画オフセット）は`init_dim()`が検出した不透明ピクセルの
  バウンディングボックスから自動計算され、かつ`node.write_uint8/uint16`で**符号なし**として
  書き込まれる（130〜140行目付近）。つまりmakeobj側にはマイナスオフセットを指定する手段が
  なく、256×256画像をそのまま使うと「画像の左上を基準に、128×128画像の2倍のピクセル数を
  同じ基準点から描画する」ことになり、実質的に建物が本来のタイル位置から南東方向へ
  半タイル分ズレて表示される（`plateau_building/README.md`のstep3/4で修正した
  「表示位置の北東寄り」と同種のアンカーバグを新たに作り込むことになる）
- 一方、256×256は「128×128の座標系を2倍ズームしただけ」なので、単純にLANCZOSで128×128へ
  戻せば、`plateau_building.dat`で既に実機確認済み（ユーザーより「狙った通りの位置に表示
  できている」と確認済み）の接地アンカー座標系にそのまま一致する。追加のオフセット計算が
  一切不要になるため、この方式を採用した
- トレードオフ: 生成された装飾（花のディテール）はダウンスケールにより多少ぼやけるが、
  最終的にSimutrans側で128px単位のタイルとして表示される以上、実用上の影響は小さいと判断した

### 3. 4隅マーカーによるクロップ位置の固定化

`plateau_building/README.md`step3の知見（makeobjは不透明ピクセルのbboxで自動クロップするため、
画像が全域不透明でないと予期しないオフセットが生じる）を踏まえ、ダウンスケール後の画像を
検証した。

```
downscaled corner alpha (TL,TR,BL,BR): 209 209 209 209
```

候補画像はもともと`building.png`（4隅に不透明1pxマーカー焼き込み済み）をベースに生成された
ため、256×256版の時点で4隅は既にalpha=255だったが、256→128のLANCZOSダウンスケールで
209まで低下していた（229は完全不透明ではないため、makeobjの不透明判定閾値次第ではbboxが
縮む可能性があった）。念のため`plateau_building`と同じ対策として、ダウンスケール後の画像の
4隅ピクセルを`(0,0,0,255)`で強制的に上書きし、128×128フルキャンバスでの検出を保証した。

### 4. dat作成

`try-out/plateau_building/plateau_building.dat`をベースに、`name`/`copyright`を変更し、
`BackImage[0]`〜`[3]`の参照先を`building.png`（新規の装飾済み画像）に差し替えた
（[`t2i_addon_final.dat`](t2i_addon_final.dat)）。`cursor`/`icon`は
`try-out/plateau_building/building_icon.png`をそのままコピーして流用した（新規生成なし）。

### 5. 検証

- `dat_linter lint t2i_addon_final.dat` → **エラー・警告なし（exit 0）**
- `makeobj VERBOSE DEBUG pak128 t2i_addon_final.pak t2i_addon_final.dat` → **成功（exit 0）**。
  image debugログは4レイアウトすべてで
  ```
  image[  0] =building.png.0.0    building.png    0  0  0  0  128  128  yes
  ```
  （列は `X Y OffX OffY Width Height`）となり、`plateau_building.dat`修正後の既知良好値
  （`0 0 0 0 128 128`）と完全に一致した。クロップ起因のオフセットは発生していない

### 6. 配置

生成した`t2i_addon_final.pak`を`E:\simutrans_addon\simuwin\addons\pak128\t2i_addon_final.pak`
に配置した（既存の`plateau_building.pak`等は上書きしていない）。

## 得られた知見や失敗

- **t2i生成パイプラインの中間解像度（2倍supersampling等）は、そのままpak化用画像として
  使うべきではない**。`FINAL_SCALE`のような生成品質向上のための拡大率は、最終的に
  ゲーム内の標準タイル解像度（pak128なら128×128）へ戻してから`.dat`に組み込む必要がある。
  理由はmakeobjの`image.x`/`image.y`が符号なし整数でありオフセットを負の方向に指定できない
  ため、「同じ描画基準点から2倍のピクセル数を描く」ことがそのまま「タイル位置が半タイル分
  南東へズレる」という新しいアンカーバグに直結する
- **4隅への不透明1pxマーカーは、リサイズ処理を挟むとalphaが減衰しうる**（今回256→128の
  LANCZOSダウンスケールで255→209まで低下）。makeobj投入前の最終画像に対して、リサイズ等の
  後処理をすべて終えた後で改めてマーカーを焼き直す（上書きする）のが確実
  （`plateau_building`のstep3の技法を「生成した最終画像」に対しても再適用する形になる）
- `plateau_building.dat`で確立された接地アンカー座標系（画像下端から32px = row96が接地点）に
  は依存せず、単純に「同じ128×128座標系のまま画像だけ差し替える」方針を貫けたため、
  接地位置ズレの新規デバッグは今回発生しなかった。座標系を変えずに済ませることが
  結果的に一番のリスク回避策だった

## ゲーム内での確認結果

ユーザーがSimutrans上で実際に設置し、**「表示OK」**と確認済み（2026-07-09）。
以下は確認時に使った手順（再現用に記録）。

1. Simutransを起動し、pak128セーブ/新規マップを開く
2. 建設メニュー（鉄道関連、駅の拡張建物カテゴリ）を開き、`t2i_addon_final_53394515`という
   名前のアドオンを探す（アイコンは`plateau_building`と同じPLATEAU建物のサムネイル）
3. 既存の線路・駅に隣接させて設置し、建物の左辺（南西〜西側）に紫〜ピンクの花壇状の
   装飾が建物本体に沿って表示されるかを確認する
4. 比較用に、同じ場所に`plateau_building`（装飾なしの元建物、`plateau_building.pak`）も
   併せて設置し、接地位置・スケールが装飾版と一致しているか（今回の128×128
   ダウンスケール処理で座標系がズレていないか）を見比べることを推奨する
