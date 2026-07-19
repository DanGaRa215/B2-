# utils

DB の状態を確認するためのスクリプト。

| スクリプト | 用途 |
|---|---|
| `show_tables.py` | public スキーマのテーブル一覧を表示 |
| `check_db.py` | 各テーブルのレコード数を表示 |

上記はいずれも読み取り専用で、DB を変更しない。

## ⚠️ dangerous/

`dangerous/` 配下のスクリプトは **DB を破壊的に変更する**。確認プロンプトは無く、
実行した瞬間に削除が走る。

| スクリプト | 影響 |
|---|---|
| `clear_all_vectors.py` | `store_vectors` と **`review_vectors` を全削除**。review_vectors は約16GB・300万件規模で、**再生成には数日かかる** |
| `clear_vectors.py` | `store_vectors` を全削除（現在0件のため影響は軽微） |

実行前に必ずバックアップを取ること。

```bash
/opt/homebrew/opt/postgresql@15/bin/pg_dump -d tabelog_db \
  -t reviews -t review_clusters -t cluster_centroids -t stores \
  -f ~/tabelog_backup_$(date +%Y%m%d).sql
```
