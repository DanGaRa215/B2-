"""
類似度の分布を分析
"""
from recommender import StoreRecommender
import numpy as np

def analyze_similarity():
    recommender = StoreRecommender()

    # テストクエリ
    queries = [
        "静かで落ち着いた雰囲気でデート",
        "賑やかで楽しい雰囲気で女子会",
        "あっさりしていて体に優しいもの",
        "濃厚でガッツリ食べられる"
    ]

    print("="*80)
    print("類似度分布の分析")
    print("="*80)

    for query in queries:
        print(f"\n【クエリ】: {query}")
        print("-"*80)

        # クエリベクトル生成
        query_vector = recommender._encode_query(query)

        # 全店舗との類似度計算
        from sklearn.metrics.pairwise import cosine_similarity
        similarities = cosine_similarity(query_vector, recommender.store_vectors)[0]

        # 統計情報
        print(f"類似度の統計:")
        print(f"  最大値: {similarities.max():.4f}")
        print(f"  最小値: {similarities.min():.4f}")
        print(f"  平均値: {similarities.mean():.4f}")
        print(f"  標準偏差: {similarities.std():.4f}")
        print(f"  中央値: {np.median(similarities):.4f}")

        # TOP5の類似度
        top5_indices = np.argsort(similarities)[::-1][:5]
        print(f"\n  TOP5の類似度:")
        for i, idx in enumerate(top5_indices, 1):
            print(f"    {i}位: {recommender.store_names[idx]:30s} - {similarities[idx]:.4f}")

        # 類似度の分布（10分位）
        print(f"\n  類似度の分布:")
        for percentile in [10, 25, 50, 75, 90]:
            val = np.percentile(similarities, percentile)
            print(f"    {percentile}%ile: {val:.4f}")

if __name__ == "__main__":
    analyze_similarity()
