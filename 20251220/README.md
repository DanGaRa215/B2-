# 食べログ推薦システム

自然文のクエリ（「デートで使える落ち着いた雰囲気の店」など）から、
レビューの内容が近い店舗を推薦する。

レビューを個別に SimCSE でベクトル化してクラスタリングし、
クエリに近いクラスタからレビューを集めて店舗をスコアリングする。
手法の詳細は [README_提案手法.md](README_提案手法.md) を参照。

## ディレクトリ

| | 内容 |
|---|---|
| [`pipeline/`](pipeline/) | 本処理。番号順に実行する。[実行手順](pipeline/README.md) |
| [`utils/`](utils/) | DB の状態確認。`dangerous/` は破壊的なので注意 |
| `debug/` | 各工程の調査用スクリプト |
| `notebooks/` | Jupyter Notebook |
| [`deprecated/`](deprecated/) | 現行から参照されていない旧実装。削除予定 |
| `data/` | スクレイピング済み CSV（git 管理外・約1.2GB） |

## 環境

- PostgreSQL 15（`postgresql@15`）— DB名 `tabelog_db`
- Python 3.10（`.venv/`）
- 埋め込みモデル: `pkshatech/simcse-ja-bert-base-clcmlp`（768次元）

`psql` は PATH に無いため、DB を直接触るときは
`/opt/homebrew/opt/postgresql@15/bin/` 配下を使うか psycopg2 経由で行う。

```bash
.venv/bin/python 20251220/utils/show_tables.py   # テーブル一覧
.venv/bin/python 20251220/utils/check_db.py      # レコード数
```

## テーブル

| テーブル | 内容 |
|---|---|
| `stores` | 店舗の基本情報 |
| `reviews` | レビュー本文 |
| `review_vectors` | レビューごとの768次元ベクトル |
| `review_clusters` | レビューのクラスタ割り当て |
| `cluster_centroids` | 各クラスタの重心ベクトル |
| `store_vectors`, `store_vector_clusters` | 旧実装のもの。現在は未使用（0件） |

`review_vectors` と `review_clusters` は `reviews` への外部キーを持たない。
レビューを削除しても連動して消えないため、孤児行は手動で削除する必要がある。
