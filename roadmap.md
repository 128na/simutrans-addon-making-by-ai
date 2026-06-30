# Roadmap

## 最終目標
pakセット作成（全タイプのアドオンが作成できる状態）

## 現在のブロッカー
- 画像生成をどうするか（現状：Blenderヘッドレスレンダリングで PoC 完了）
- アドオン形式によるバリエーションが多い（車両・建物・軌道で生成すべき画像パターンが大きく異なる）

## 採用パイプライン
```
テキスト/スクリプト
→ Blender ヘッドレス（約2秒）→ PNG（128×128 RGBA）
→ dat 作成 → makeobj pak128 → .pak → Simutrans ゲーム内表示
```

**2D直接生成でなくBlender経由にした理由**
- 2D生成AIはイソメトリック角度の再現が不安定
- Blender経由なら角度を数学的に固定できる
- 同じ3Dモデルから複数方向を一括生成できる（車両対応時に有効）

## アドオンタイプ別画像複雑度
| タイプ | 画像枚数 | 対応状況 |
|--------|---------|----------|
| groundobj（地面装飾） | 1枚 | 未 |
| attraction_land | 1〜4枚 | 未 |
| building（駅拡張） | 4枚（方向別） | ✓ PoC 完了 |
| city building | 4枚 | 未 |
| vehicle（車両） | 8方向 × 状態数 | ✓ PoC 完了（0系新幹線, 簡易形状） |
| way（軌道） | 直線・カーブ・分岐... | 未 |

## TODO

### 近期
- [ ] 4方向で異なる画像を使う（現状は4方向とも同一画像）
- [ ] より複雑な形状（実際の建物モデル）の生成テスト
- [ ] dat ファイル自動生成との接続（LLM連携）
- [ ] groundobj など他のアドオンタイプへの展開

### 中期
- [ ] 複数タイルサイズ対応（2×2、3×3 など）
- [ ] 車両モデルの作り込み（窓・パンタグラフ・台車の精密化、編成中間車・最後尾車）
- [ ] 車両方向マッピングのキャリブレーション工程をスクリプト化（手作業の往復を削減）

### 長期（別フェーズ）
- [x] **formatter / linter / 静的解析（PoC）** — `try-out/dat_linter/`（Rust）
  - formatter (`dat_linter fmt`): キー正規化・並び替え。`obj=building`非依存の汎用実装
  - linter (`dat_linter`): `obj=building`の`type=extension`/`stop`/`depot`系のみ対応完了
  - 静的解析 (`dat_linter couplings`): vehicle dat の連結制約(`constraint[prev/next]`)
    充足可能性解析のPoC完了
  - [ ] `vehicle`本体（building以外）/`way` など他obj種別のlinter対応
  - [ ] 静的解析: 連結制約以外のランタイム依存問題（speed=0等）はランタイムコード調査から要着手
  - [ ] OSS公開に向けた `cargo test` 化・CI整備
