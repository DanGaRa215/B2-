# deprecated

現行のパイプラインから使われていないコード。動作確認が済んだら削除してよい。

## old_recommend_system/

`pipeline/05_recommendation/recommend.py` の前身にあたる旧推薦システム。
現行版とは設計が別系統で、現行版からは一切参照していない。

| | 旧 (`recommender.py`) | 現行 (`recommend.py`) |
|---|---|---|
| モデル | `cl-tohoku/bert-base-japanese-v3` | `pkshatech/simcse-ja-bert-base-clcmlp` |
| 参照テーブル | `store_vectors` | `review_vectors` + クラスタ |
| 評価の正規化 | 3.0〜5.0 | 1.0〜5.0 |

参照先の `store_vectors` は現在 **0件** で、この系統は動作しない。

3ファイルは相互に依存しているため**まとめて扱うこと**。
`analyze_similarity.py` と `test_recommender.ipynb` が
`from recommender import StoreRecommender` で読み込んでいる（同一ディレクトリ前提）。

## old_import/

`import_csv_to_db.py` / `import_csv_debug.py` はどちらも
`tabelog_tokyo_all.csv` を読むが、**このファイルは存在しない**。実行不能。
現行のインポートは `pipeline/02_import/import_all_csv.py`。

## migrations/

`drop_column.py` は `reviews` から `review_rating` を削除する一回限りの移行スクリプト。
適用済み。

## cleanup_old_centroids.py

`cluster_centroids` から `cluster_id >= 50` を削除する。K=50 時代に書かれたもので、
**閾値が現在の K と合っていない**（K=35 なら 35〜49 が取り残される）。

`pipeline/04_clustering/review_clustering.py` の `save_centroids()` が
古い重心を削除するよう修正されれば、このスクリプト自体が不要になる。
