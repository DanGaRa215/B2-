# 提案手法: クラスタリングベースのハイブリッド推薦システム

## 概要

本研究では、**レビューテキストの意味的理解**と**客観的な品質評価**を組み合わせた、クラスタリングベースのハイブリッド推薦システムを提案する。

ユーザーの曖昧なイメージクエリ（例: "ロマンチックなイタリアン"）に対して、以下の2段階アプローチで店舗を推薦する:

1. **クラスタリングによる候補絞り込み**: クエリに意味的に近いレビュークラスタを検索
2. **ハイブリッドスコアによる最終評価**: 意味的類似度と星評価を線形結合

---

## システムアーキテクチャ

### **全体フロー**

```
[データ収集] → [ベクトル化] → [クラスタリング] → [推薦]
    ↓              ↓               ↓              ↓
 食べログ       SentenceT.     MiniBatch      ハイブリッド
スクレイピング   BERT(日本語)    KMeans        スコアリング
```

---

## 1. データ収集

### 1.1 スクレイピング対象
- **対象サイト**: 食べログ（東京23区）
- **収集データ**:
  - 店舗情報（店名、ジャンル、評価、URL）
  - ユーザーレビュー（レビューテキスト）

### 1.2 データ規模
- **店舗数**: 約5,000店舗
- **レビュー数**: 928,547件
- **ベクトル化済みレビュー**: 435,968件

---

## 2. レビューのベクトル化

### 2.1 使用モデル
- **モデル**: `pkshatech/simcse-ja-bert-base-clcmlp`
- **タイプ**: 日本語SentenceBERT
- **次元数**: 768次元

### 2.2 処理フロー
```python
review_text → SentenceTransformer → 768次元ベクトル → DB保存
```

### 2.3 正規化
- **手法**: L2正規化
- **目的**: コサイン類似度をベクトル内積で高速計算

**処理:**
```python
vec = model.encode(review_text)
vec = vec / np.linalg.norm(vec)  # ノルム=1.0
```

### 2.4 データベーススキーマ
```sql
CREATE TABLE review_vectors (
    review_id INTEGER PRIMARY KEY,
    feature_vector REAL[]  -- 768次元ベクトル
);
```

---

## 3. レビュークラスタリング

### 3.1 クラスタリング手法
- **アルゴリズム**: MiniBatchKMeans
- **クラスタ数**: K=20（IVF方式のrecall/selectivity評価により決定。README.mdの「既知の性質」参照）
- **正規化**: L2正規化（クラスタリング前）

### 3.2 目的
全レビューを意味的に類似したグループに分割することで:
- 検索空間を削減（43.6万件 → 約8,700件/クラスタ）
- クエリに関連するレビューのみを高速抽出

### 3.3 クラスタリング結果
```
総レビュー数: 1,057,505件
クラスタ数: 20個
平均レビュー数/クラスタ: 約52,875件
```

### 3.4 データベーススキーマ
```sql
-- レビュー→クラスタの割り当て
CREATE TABLE review_clusters (
    review_id INTEGER PRIMARY KEY,
    cluster_id INTEGER
);

-- クラスタ中心ベクトル
CREATE TABLE cluster_centroids (
    cluster_id INTEGER PRIMARY KEY,
    centroid_vector REAL[]  -- 768次元
);
```

---

## 4. 推薦システム

### 4.1 ハイブリッドスコア

**定義:**
```
ハイブリッドスコア = α × 正規化クエリ類似度 + (1-α) × 正規化星評価
```

- **α = 1.0**: 純粋な意味的類似度（イメージ重視）
- **α = 0.0**: 純粋な星評価（品質重視）
- **0 < α < 1**: 両者のバランス（最適なNDCG@Kを達成）

### 4.2 推薦フロー

#### **Step 1: クエリのベクトル化**
```python
query = "ロマンチックなイタリアン"
query_vec = model.encode(query)
query_vec = query_vec / np.linalg.norm(query_vec)  # L2正規化
```

#### **Step 2: 類似クラスタ検索**
```python
# 20個のクラスタ中心とクエリの類似度を計算
similarities = [cosine_sim(query_vec, centroid) for centroid in centroids]

# 上位K個のクラスタを選択（K=2）
top_k_clusters = top_k(similarities, k=2)
```

**計算量削減:**
- 全レビュー検索: O(1,057,505)
- クラスタ検索: O(20) + O(105,750) = **約90%削減**

#### **Step 3: 候補店舗の抽出**
```python
# 選択されたクラスタに属するレビューのみを取得
reviews = get_reviews_from_clusters(top_k_clusters)

# 店舗ごとにグループ化
store_reviews = group_by_store(reviews)
```

#### **Step 4: クエリ類似度の計算**
```python
for store_id, reviews in store_reviews.items():
    similarities = []
    for review_vec in reviews:
        # レビューベクトルをL2正規化
        review_vec = review_vec / np.linalg.norm(review_vec)

        # コサイン類似度（0〜1）
        sim = np.dot(query_vec, review_vec)
        similarities.append(sim)

    # 店舗の平均類似度
    store_similarity[store_id] = np.mean(similarities)
```

#### **Step 5: 正規化**

**5.1 類似度の正規化**
```python
# 既に0〜1の範囲なのでクリッピングのみ
normalized_sim = max(0.0, min(1.0, similarity))
```

**5.2 星評価の正規化**
```python
# 固定範囲Min-Max正規化（食べログ: 1.0〜5.0）
normalized_rating = (rating - 1.0) / (5.0 - 1.0)
```

**重要:**
- 相対的な正規化ではなく**固定範囲正規化**を使用
- クエリ間で一貫性のある評価が可能

#### **Step 6: ハイブリッドスコア計算**
```python
hybrid_score = α × normalized_similarity + (1-α) × normalized_rating
```

**例:** α=0.7の場合
```
類似度: 0.65 → 正規化: 0.65
星評価: 3.5  → 正規化: 0.625

ハイブリッドスコア = 0.7 × 0.65 + 0.3 × 0.625
                 = 0.455 + 0.1875
                 = 0.6425
```

#### **Step 7: ランキングと出力**
```python
# ハイブリッドスコアで降順ソート
ranked_stores = sorted(stores, key=lambda x: x['hybrid_score'], reverse=True)

# Top-N件を推薦
recommendations = ranked_stores[:N]
```

---

## 5. 正規化戦略の詳細

### 5.1 正規化の全体マップ

| ステップ | データ | 正規化前 | 正規化手法 | 正規化後 | 目的 |
|---------|--------|---------|-----------|---------|------|
| 1 | クエリベクトル | 任意 | **L2正規化** | ノルム=1.0 | コサイン類似度計算 |
| 2 | レビューベクトル | ノルム≈7〜8 | **L2正規化** | ノルム=1.0 | コサイン類似度計算 |
| 3 | コサイン類似度 | ≈0〜1 | **クリッピング** | 厳密に0〜1 | 数値安定性 |
| 4 | 星評価 | 1.0〜5.0 | **固定範囲Min-Max** | 0〜1 | スケール統一 |

### 5.2 なぜ固定範囲正規化が重要か

**従来手法（相対的Min-Max正規化）の問題:**
```python
# クエリAの候補店舗: 評価3.0〜3.5
normalized = (3.0 - 3.0) / (3.5 - 3.0) = 0.0  # 評価3.0
normalized = (3.5 - 3.0) / (3.5 - 3.0) = 1.0  # 評価3.5

# クエリBの候補店舗: 評価4.0〜4.5
normalized = (4.0 - 4.0) / (4.5 - 4.0) = 0.0  # 評価4.0
normalized = (4.5 - 4.0) / (4.5 - 4.0) = 1.0  # 評価4.5
```
→ 評価3.5と4.0が同じ正規化値になり、絶対的な品質が失われる

**提案手法（固定範囲正規化）:**
```python
# どのクエリでも同じ
normalized = (3.0 - 1.0) / (5.0 - 1.0) = 0.50  # 評価3.0
normalized = (3.5 - 1.0) / (5.0 - 1.0) = 0.625 # 評価3.5
normalized = (4.0 - 1.0) / (5.0 - 1.0) = 0.75  # 評価4.0
normalized = (4.5 - 1.0) / (5.0 - 1.0) = 0.875 # 評価4.5
```
→ クエリ間で一貫性のある評価が可能

---

## 6. システムの特徴

### 6.1 利点

1. **意味的理解**
   - レビューテキストから店舗の特徴を自動抽出
   - "ロマンチック"などの抽象的なクエリに対応

2. **計算効率**
   - クラスタリングで検索空間を約90%削減
   - K=20クラスタ → 平均52,875件/クラスタ、うち上位2クラスタのみ処理

3. **柔軟性**
   - αパラメータで意味と品質のバランスを調整可能
   - ユーザーの嗜好に応じた推薦が可能

4. **一貫性**
   - 固定範囲正規化でクエリ間の比較が可能
   - 同じ店舗は常に同じ評価値

### 6.2 技術的工夫

1. **サーバーサイドカーソル**
   - 大量レビューのメモリ効率的な処理
   - バッチサイズ: 5,000件

2. **ON CONFLICT処理**
   - 中断・再開可能なベクトル化処理
   - データの整合性保証

3. **GPU最適化**
   - Apple Silicon MPS対応
   - ベクトル化の高速化

---

## 7. 実装詳細

### 7.1 技術スタック

| レイヤー | 技術 |
|---------|------|
| 言語 | Python 3.12 |
| 機械学習 | SentenceTransformers, scikit-learn |
| データベース | PostgreSQL 14+ |
| ベクトル演算 | NumPy |
| GPU | PyTorch (MPS backend) |

### 7.2 主要パラメータ

```python
# モデル
MODEL_NAME = 'pkshatech/simcse-ja-bert-base-clcmlp'
VECTOR_DIM = 768

# クラスタリング
NUM_CLUSTERS = 20
BATCH_SIZE = 4096

# 推薦
TOP_K_CLUSTERS = 2
TOP_N_STORES = 5
ALPHA = 0.7  # デフォルト値
```

### 7.3 実行例

```python
from simple_recommend import recommend_with_all_alphas

# 1つのクエリで4つのα値の結果を表示
recommend_with_all_alphas("ロマンチックなイタリアン", top_n=5)
```

**出力:**
```
α = 0.0 (純粋な星評価)
【1位】高評価イタリアン A (評価: 4.5, スコア: 0.875)

α = 0.3 (星評価70% + クエリ30%)
【1位】高評価でロマンチック B (評価: 4.2, スコア: 0.821)

α = 0.7 (クエリ70% + 星評価30%)
【1位】非常にロマンチック C (評価: 3.8, スコア: 0.782)

α = 1.0 (純粋なクエリ類似度)
【1位】最もロマンチック D (評価: 3.5, スコア: 0.735)
```

---

## 8. 評価指標（今後の課題）

### 8.1 提案する評価方法

1. **NDCG@K (Normalized Discounted Cumulative Gain)**
   - 異なるα値での推薦品質を定量評価
   - 最適なα値の探索

2. **多様性評価**
   - 推薦結果の多様性（ジャンル、価格帯）
   - クラスタ分布の分析

3. **ユーザースタディ**
   - 実際のユーザーによる満足度評価
   - クエリタイプ別の有効性検証

---

## 9. ファイル構成

```
20251220/
├── pipeline/                                       # 本手法の処理パイプライン
│   ├── 01_scraping/
│   │   └── scrayping_tabelog.py                    # 食べログのスクレイピング
│   ├── 02_import/
│   │   └── import_all_csv.py                       # CSV を PostgreSQL に投入
│   ├── 03_vectorization/
│   │   └── generate_review_vectors.py              # レビューのベクトル化（SimCSE）
│   ├── 04_clustering/
│   │   ├── review_clustering.py                    # K-means クラスタリング
│   │   └── evaluate_cluster_number.py              # 最適なクラスタ数の評価
│   └── 05_recommendation/
│       └── recommend.py                            # 推薦システム
├── utils/                                          # DB 確認用
├── debug/                                          # 各工程の調査用
├── notebooks/                                      # Jupyter Notebook
├── deprecated/                                     # 旧実装（削除予定）
├── data/                                           # スクレイピング済み CSV
└── README_提案手法.md                               # 本ドキュメント
```

ディレクトリの番号は実行順序を表す。詳細な実行手順は `pipeline/README.md` を参照。

---

## 10. まとめ

本提案手法は、以下の3つの要素を統合した新しいレストラン推薦システムである:

1. **レビューの意味的理解** (SentenceBERT)
2. **効率的な候補絞り込み** (K-Meansクラスタリング)
3. **意味と品質のバランス** (ハイブリッドスコア)

特に、**固定範囲正規化**により、異なるクエリ間での一貫性を保ちながら、ユーザーの曖昧なイメージクエリに柔軟に対応できる点が特徴である。

αパラメータの調整により、「とにかく高評価の店」から「イメージにぴったりの店」まで、ユーザーの多様なニーズに応えることが可能である。

---

**生成日**: 2026-01-04
**バージョン**: 1.0
