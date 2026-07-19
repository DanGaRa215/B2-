#!/usr/bin/env python3
"""
簡単な推薦システム実行スクリプト

1つのクエリを入力するだけで、α = 0.0, 0.3, 0.7, 1.0 の4つの結果を表示
"""

import sys
sys.path.append('/Users/dangararara/lecture/miraisouzou/20251220/recommend')

# ノートブックから関数をインポート（実際にはコピー）
import numpy as np
import psycopg2
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Dict
import torch

# ========== 設定 ==========
DB_HOST = "localhost"
DB_NAME = "tabelog_db"
DB_USER = "dangararara"

MODEL_NAME = 'pkshatech/simcse-ja-bert-base-clcmlp'
TOP_K_CLUSTERS = 10
TOP_N_STORES = 5

# モデル初期化
print(f"モデル読み込み中: {MODEL_NAME}")
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = SentenceTransformer(MODEL_NAME, device=device)
print(f"デバイス: {device}\n")

def connect():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER)

def vectorize_query(query: str) -> np.ndarray:
    vec = model.encode([query], convert_to_numpy=True, show_progress_bar=False)[0]
    vec = vec / np.linalg.norm(vec)
    return vec

def load_cluster_centroids(conn) -> Dict[int, np.ndarray]:
    cur = conn.cursor()
    cur.execute("SELECT cluster_id, centroid_vector FROM cluster_centroids ORDER BY cluster_id")
    centroids = {}
    for cluster_id, centroid_vec in cur:
        centroids[cluster_id] = np.array(centroid_vec, dtype=np.float32)
    return centroids

def find_similar_clusters(query_vec: np.ndarray, centroids: Dict[int, np.ndarray], top_k: int) -> List[Tuple[int, float]]:
    similarities = []
    for cluster_id, centroid in centroids.items():
        sim = np.dot(query_vec, centroid)
        similarities.append((cluster_id, float(sim)))
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_k]

def get_reviews_from_clusters(conn, cluster_ids: List[int]) -> Dict[str, List[Tuple[int, np.ndarray]]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT rv.review_id, r.store_id, rv.feature_vector
        FROM review_vectors rv
        JOIN reviews r ON rv.review_id = r.review_id
        JOIN review_clusters rc ON rv.review_id = rc.review_id
        WHERE rc.cluster_id = ANY(%s) AND rv.feature_vector IS NOT NULL
    """, (cluster_ids,))

    store_reviews = {}
    for review_id, store_id, feature_vec in cur:
        if store_id not in store_reviews:
            store_reviews[store_id] = []
        vec = np.array(feature_vec, dtype=np.float32)
        store_reviews[store_id].append((review_id, vec))
    return store_reviews

def calculate_store_similarity(query_vec: np.ndarray, store_reviews: Dict[str, List[Tuple[int, np.ndarray]]]) -> Dict[str, float]:
    store_similarities = {}
    for store_id, reviews in store_reviews.items():
        similarities = []
        for _, vec in reviews:
            # レビューベクトルをL2正規化
            vec_norm = np.linalg.norm(vec)
            if vec_norm > 0:
                vec = vec / vec_norm
            # コサイン類似度を計算（0〜1の範囲）
            sim = float(np.dot(query_vec, vec))
            similarities.append(sim)
        store_similarities[store_id] = np.mean(similarities)
    return store_similarities

def normalize_similarities(similarities: Dict[str, float]) -> Dict[str, float]:
    """
    類似度を正規化（既に0〜1の範囲なのでクリッピングのみ）
    """
    normalized = {}
    for store_id, sim in similarities.items():
        # 0〜1の範囲にクリッピング
        normalized[store_id] = max(0.0, min(1.0, sim))
    return normalized

def normalize_ratings(ratings: Dict[str, float]) -> Dict[str, float]:
    """
    星評価を固定範囲(1.0〜5.0)で正規化
    """
    if not ratings:
        return {}
    normalized = {}
    for store_id, rating in ratings.items():
        # 食べログの評価範囲: 1.0〜5.0
        rating = max(1.0, min(5.0, rating))
        normalized[store_id] = (rating - 1.0) / (5.0 - 1.0)
    return normalized

def calculate_hybrid_scores(conn, query_vec: np.ndarray, cluster_ids: List[int], alpha: float) -> List[Dict]:
    store_reviews = get_reviews_from_clusters(conn, cluster_ids)
    store_similarities = calculate_store_similarity(query_vec, store_reviews)

    cur = conn.cursor()
    cur.execute("""
        SELECT store_id, store_name, genre, overall_rating, store_url
        FROM stores
        WHERE store_id = ANY(%s)
    """, (list(store_similarities.keys()),))

    store_info = {}
    store_ratings = {}
    for store_id, store_name, genre, rating, store_url in cur:
        store_info[store_id] = {
            'store_id': store_id,
            'store_name': store_name,
            'genre': genre,
            'rating': rating,
            'store_url': store_url
        }
        store_ratings[store_id] = rating if rating else 0.0

    # 類似度を正規化（0〜1にクリッピング）
    normalized_similarities = normalize_similarities(store_similarities)
    # 星評価を固定範囲(1.0〜5.0)で正規化
    normalized_ratings = normalize_ratings(store_ratings)

    hybrid_scores = []
    for store_id in store_similarities:
        norm_similarity = normalized_similarities.get(store_id, 0.0)
        norm_rating = normalized_ratings.get(store_id, 0.0)
        hybrid_score = alpha * norm_similarity + (1 - alpha) * norm_rating

        info = store_info[store_id].copy()
        info['similarity_score'] = norm_similarity
        info['normalized_rating'] = norm_rating
        info['hybrid_score'] = hybrid_score
        hybrid_scores.append(info)

    hybrid_scores.sort(key=lambda x: x['hybrid_score'], reverse=True)
    return hybrid_scores

def get_sample_reviews(conn, store_id: str, cluster_ids: List[int], limit: int = 2) -> List[str]:
    cur = conn.cursor()
    cur.execute("""
        SELECT r.review_text
        FROM reviews r
        JOIN review_clusters rc ON r.review_id = rc.review_id
        WHERE r.store_id = %s AND rc.cluster_id = ANY(%s) AND r.review_text IS NOT NULL
        LIMIT %s
    """, (store_id, cluster_ids, limit))
    return [row[0] for row in cur.fetchall()]

# ========== メイン関数: 1クエリで4つのα値を実行 ==========
def recommend_with_all_alphas(query: str, top_n: int = 5):
    """
    1つのクエリで α = 0.0, 0.3, 0.7, 1.0 の4つの結果を表示

    Args:
        query: 検索クエリ
        top_n: 各α値で推薦する店舗数
    """
    print("=" * 80)
    print(f"クエリ: 「{query}」")
    print("=" * 80)

    # 事前処理（1回だけ実行）
    print("\n[事前処理] クエリのベクトル化とクラスタ検索...")
    query_vec = vectorize_query(query)

    conn = connect()
    centroids = load_cluster_centroids(conn)
    similar_clusters = find_similar_clusters(query_vec, centroids, top_k=TOP_K_CLUSTERS)
    cluster_ids = [c[0] for c in similar_clusters]

    print(f"類似クラスタ (Top {TOP_K_CLUSTERS}):", end=" ")
    print(", ".join([f"cluster_{cid}" for cid, _ in similar_clusters[:5]]) + "...")

    # 4つのα値で推薦
    alpha_values = [0.0, 0.3, 0.7, 1.0]

    for alpha in alpha_values:
        print("\n" + "=" * 80)
        print(f"α = {alpha} (クエリ類似度: {alpha*100:.0f}%, 星評価: {(1-alpha)*100:.0f}%)")
        print("=" * 80)

        ranked_stores = calculate_hybrid_scores(conn, query_vec, cluster_ids, alpha=alpha)
        top_stores = ranked_stores[:top_n]

        for i, store in enumerate(top_stores, 1):
            print(f"\n【{i}位】 {store['store_name']}")
            print(f"  ジャンル: {store['genre']}")
            print(f"  評価: {store['rating']}")
            print(f"  URL: {store['store_url']}")
            print(f"  ハイブリッドスコア: {store['hybrid_score']:.4f}")
            print(f"    - クエリ類似度: {store['similarity_score']:.4f}")
            print(f"    - 正規化評価: {store['normalized_rating']:.4f}")

            # レビュー例を2件表示
            reviews = get_sample_reviews(conn, store['store_id'], cluster_ids, limit=2)
            if reviews:
                print(f"  レビュー例:")
                for j, review in enumerate(reviews, 1):
                    preview = review[:80] + "..." if len(review) > 80 else review
                    print(f"    [{j}] {preview}")

    conn.close()
    print("\n" + "=" * 80)

# ========== 実行 ==========
if __name__ == "__main__":
    # ここにクエリを入力するだけ！
    recommend_with_all_alphas("デートで使える落ち着いた雰囲気の店", top_n=5)

    recommend_with_all_alphas("気軽にコスパよく友達と行ける", top_n=5)