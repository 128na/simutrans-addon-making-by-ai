# Blenderヘッドレスレンダリング検証

作業日: 2026-06-30

## 目標
Blenderをヘッドレスで動かし、Simutransのイソメトリック視点でPNGを出力できるか確認する

## 結果
達成

## 試したこと
- `blender --background --python script.py` でヘッドレス実行
- render engine を `BLENDER_EEVEE_NEXT` → エラー、`BLENDER_EEVEE` に修正
- `use_nodes=True` で Principled BSDF に色を設定
- カメラを手動座標で配置 → フレームがズレる問題
  - rotation から逆算する方式に変更して解決
- 仰角を 26.57°（arctan(0.5) の推定値）→ 参考資料から 30° が正しいと判明
- 高さスケール 0.816（√6/3）を適用
- 自己発光 0.25 を設定して側面の暗さを改善
- ortho_scale を 1.8 → 1.43（近似）→ `math.sqrt(2)`（正確値）と段階的に調整

## 得られた知見や失敗
- Blender 5.1 では render engine は `'BLENDER_EEVEE'`（4.x の `BLENDER_EEVEE_NEXT` は無効）
- カメラ位置は rotation 設定後に逆算する必要がある
  ```python
  bpy.context.view_layer.update()
  forward = cam.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))
  cam.location = target - forward * distance
  ```
- 1タイル(1×1 BU)を128pxにぴったり収めるには `ortho_scale = math.sqrt(2)`
- 仰角は 26.57° ではなく **30°**（Blender X rotation = 60°）が正しい
- レンダリング時間は約2秒（EEVEE）
