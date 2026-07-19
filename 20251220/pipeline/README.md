# 処理パイプライン

食べログのレビューから、クエリに合う店舗を推薦するまでの一連の処理。
ディレクトリ名の番号が実行順序を表す。

| 工程 | 入力 | 出力 |
|---|---|---|
| `01_scraping` | 食べログ | `data/*.csv` |
| `02_import` | `data/*.csv` | `stores`, `reviews` |
| `03_vectorization` | `reviews` | `review_vectors` |
| `04_clustering` | `review_vectors` | `review_clusters`, `cluster_centroids` |
| `05_recommendation` | 上記すべて | 推薦結果 |

## 実行

```bash
python pipeline/01_scraping/scrayping_tabelog.py
python pipeline/02_import/import_all_csv.py
python pipeline/03_vectorization/generate_review_vectors.py
python pipeline/04_clustering/review_clustering.py
python pipeline/05_recommendation/recommend.py
```

各スクリプトは単独実行を前提としており、互いを import しない。
ディレクトリ名が数字で始まるため `from pipeline.01_scraping import ...` は
構文エラーになる（Python の識別子は数字で始められない）。

## ⚠️ 運用上の注意

### ベクトル化を実行したら、必ずクラスタリングも実行する

`03_vectorization` だけを追加実行して `04_clustering` を回さないと、
**新しいレビューがどのクラスタにも属さない状態**になる。

推薦はクラスタ経由でレビューを引くため、割り当てが無いレビューは
**推薦の対象から完全に消える**。しかもエラーは出ないため気付きにくい。

### `import_all_csv.py` は `data/` の全 CSV を対象にする

差分取り込みではない。新しい CSV を1つ足しただけでも、全ファイルを読み直す。

### 新しい CSV を `data/` に置く前に、既存 CSV との重複を確認する

同じエリアを範囲を変えて複数回スクレイピングすると、CSV 間でレビューが重複する。
ファイル名の数値は店舗のインデックスであり、範囲が重ならなくても
中身は重複しうるため、名前からは判断できない。

## 初回構築時のみ

```bash
python pipeline/02_import/init_and_load_db.py
```

**⚠️ このスクリプトは `stores` / `reviews` / `store_vectors` を DROP する。**
確認プロンプトは無い。既存データがある状態では実行しないこと。

`reviews` を削除すると `review_vectors` は外部キーを持たないため残るが、
`review_id` の対応が失われて全ベクトルが孤児になる。約16GB・300万件規模で
再生成には数日かかる。
