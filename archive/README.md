# archive

現行の食べログ推薦システム（`20251220/`）とは別の、過去のプロジェクトと実験。

## ⚠️ experiments/ は git 管理外

`experiments/` 配下は `.gitignore` で除外されており、**git には中身が記録されていない**。
`git checkout` や `git switch` では復元できないため、下記の対応表が唯一の復元手段になる。

| 現在の場所 | 移動前の場所 | サイズ | ファイル数 |
|---|---|---|---|
| `archive/experiments/test/` | `test/` | 384K | 14 |
| `archive/experiments/TF-IDF/` | `TF-IDF/` | 7.5M | 5 |
| `archive/experiments/suku/` | `suku/` | 33M | 10 |
| `archive/experiments/recommended/` | `recommended/` | 16K | 2 |
| `archive/experiments/stop_word/` | `stop_word/` | 1.8M | 2 |
| `archive/experiments/ward_count/` | `ward_count/` | 124K | 1 |

いずれもリポジトリのルート直下にあったものを移動した。
`.gitignore` のパターンは先頭に `/` が無くどの階層にもマッチするため、移動後も除外され続ける。

## old_projects/odaiba/

お台場エリアのレビュー分析（2025年6〜7月）。`suku/` のノートブック群が生成したデータ。

## old_analyses/

TF-IDF や n-gram による特徴語抽出、雰囲気スコアリングの結果。
`archive/experiments/TF-IDF/` のノートブックが生成したもの。

## 内容の概要

- `experiments/TF-IDF/` — n-gram による頻出語・特徴語の抽出
- `experiments/suku/` — お台場エリアのスクレイピングとレビュー収集
- `experiments/stop_word/` — ストップワードリストの作成
- `experiments/ward_count/` — 単語出現頻度のランキング
- `experiments/recommended/` — コサイン類似度による推薦のデモ
- `experiments/test/` — 推薦パターンの比較実験
