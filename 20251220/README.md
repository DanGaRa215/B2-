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

`reviews` には `(store_id, md5(review_text))` の一意制約がある。
同じ店の同じ本文は 1 件しか入らない。

## 既知の性質

**クラスタは明確に分離していない。** 1,077,442 件で K を 10〜90 まで評価したが、
シルエット係数はどの K でも 0.02 前後で、エルボー法にも肘が現れない。
レビューの埋め込みが連続的に分布しており、はっきりした塊が存在しない。
K=35 は最良値との差が 0.0012 で、変更しても推薦品質は変わらない。

クラスタは「意味の異なるグループへの分割」というより、
走査するレビューを絞り込む手段として働いている（上位 10 クラスタで全体の 36%）。

**推薦の 2 つのスコアは性質が異なる。**

- 類似度: レビュー数が少ない店の値を全体平均へ寄せている（`SHRINKAGE_M`）。
  寄せないとレビュー 1 件の店が上位を独占する
- 評価: 実データの範囲（3.0〜4.36）で正規化している。理論値の 1.0〜5.0 で
  割ると差が 1/3 に圧縮される。評価が無い店は中央値として扱う
