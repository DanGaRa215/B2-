#!/usr/bin/env python3
"""
簡単な推薦システム実行スクリプト

1つのクエリを入力するだけで、α = 0.0, 0.3, 0.7, 1.0 の4つの結果を表示
"""

import numpy as np
import psycopg2
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Dict, Optional
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

    # 重心はあるがレビューが1件も割り当たっていないクラスタを検出する。
    # K を減らして再クラスタリングすると古い重心が残ることがあり、
    # そのクラスタが選ばれると何も返さないまま推薦結果が減る。
    cur.execute("SELECT DISTINCT cluster_id FROM review_clusters")
    assigned = {row[0] for row in cur}
    orphans = sorted(set(centroids) - assigned)
    if orphans:
        raise RuntimeError(
            f"レビューが割り当てられていないクラスタがあります: {orphans}\n"
            f"cluster_centroids と review_clusters が食い違っています。"
            f"pipeline/04_clustering/review_clustering.py を実行してください。"
        )
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

def normalize_ratings(ratings: Dict[str, Optional[float]]) -> Dict[str, float]:
    """
    星評価を実データの分布に合わせて正規化

    理論上の 1.0〜5.0 で割ると、実際の評価が 3.0〜4.36 に集中しているため
    正規化後の値が 0.5〜0.84 に圧縮され、店舗間の差がほとんど出なくなる。
    実データの最小値と最大値を使って 0.0〜1.0 の全域に広げる。

    評価が付いていない店舗は中央値として扱う。0.0 にすると最低評価の店より
    不利になり、α を下げたときに実質的に推薦から除外されてしまう。
    """
    if not ratings:
        return {}

    values = [r for r in ratings.values() if r is not None]
    if not values:
        return {store_id: 0.5 for store_id in ratings}

    lo, hi = min(values), max(values)
    median = sorted(values)[len(values) // 2]
    span = hi - lo

    normalized = {}
    for store_id, rating in ratings.items():
        r = median if rating is None else max(lo, min(hi, rating))
        normalized[store_id] = 0.5 if span == 0 else (r - lo) / span
    return normalized

def build_store_scores(conn, query_vec: np.ndarray, cluster_ids: List[int]) -> Dict[str, Dict]:
    """
    店舗ごとの類似度と評価を求める（α に依存しない部分）

    上位クラスタのレビューは 40 万件規模あり、ベクトルの取得だけで数 GB になる。
    α の値ごとに取り直すと同じ処理を 4 回繰り返すことになるため、
    α を含まない計算はここで 1 回だけ済ませる。
    """
    store_reviews = get_reviews_from_clusters(conn, cluster_ids)
    if not store_reviews:
        raise RuntimeError(
            f"クラスタ {cluster_ids} からレビューを1件も取得できませんでした。\n"
            f"review_clusters にこれらの cluster_id が存在しないか、"
            f"review_vectors との対応が失われている可能性があります。"
        )
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
        # None のまま渡す。normalize_ratings が中央値として扱う
        store_ratings[store_id] = rating

    normalized_similarities = normalize_similarities(store_similarities)
    normalized_ratings = normalize_ratings(store_ratings)

    scores = {}
    for store_id in store_similarities:
        if store_id not in store_info:
            continue
        info = store_info[store_id].copy()
        info['similarity_score'] = normalized_similarities.get(store_id, 0.0)
        info['normalized_rating'] = normalized_ratings.get(store_id, 0.0)
        scores[store_id] = info
    return scores


def rank_by_alpha(scores: Dict[str, Dict], alpha: float) -> List[Dict]:
    """build_store_scores の結果に α を適用して並べ替える"""
    ranked = []
    for info in scores.values():
        info = info.copy()
        info['hybrid_score'] = (
            alpha * info['similarity_score'] + (1 - alpha) * info['normalized_rating']
        )
        ranked.append(info)
    ranked.sort(key=lambda x: x['hybrid_score'], reverse=True)
    return ranked

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

    # α に依存しない計算はここで 1 回だけ行う
    print("レビューを集計中...")
    scores = build_store_scores(conn, query_vec, cluster_ids)
    print(f"対象店舗: {len(scores):,} 件")

    # 4つのα値で推薦
    alpha_values = [0.0, 0.3, 0.7, 1.0]

    for alpha in alpha_values:
        print("\n" + "=" * 80)
        print(f"α = {alpha} (クエリ類似度: {alpha*100:.0f}%, 星評価: {(1-alpha)*100:.0f}%)")
        print("=" * 80)

        ranked_stores = rank_by_alpha(scores, alpha)
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