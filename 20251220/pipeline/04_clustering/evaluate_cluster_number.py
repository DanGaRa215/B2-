#!/usr/bin/env python3
"""
最適なクラスタ数を評価

エルボー法とシルエット係数で評価
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from pathlib import Path

import numpy as np
import psycopg2
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sklearn.preprocessing import normalize
import matplotlib.pyplot as plt

DB_HOST = "localhost"
DB_NAME = "tabelog_db"
DB_USER = "dangararara"

def connect():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER)

def load_sample_vectors(sample_size=50000):
    """
    サンプルベクトルを読み込み（全データは重いので）
    """
    conn = connect()
    cur = conn.cursor()

    print(f"サンプルベクトル読み込み中（{sample_size:,}件）...")
    cur.execute(f"""
        SELECT feature_vector
        FROM review_vectors
        WHERE feature_vector IS NOT NULL
        ORDER BY random()
        LIMIT {sample_size}
    """)

    vectors = []
    for (vec,) in cur:
        vectors.append(np.array(vec, dtype=np.float32))

    conn.close()

    # L2正規化
    X = np.array(vectors)
    X = normalize(X, norm='l2')

    print(f"読み込み完了: {X.shape}")
    return X

def evaluate_clusters(X, k_values=[10, 20, 30, 40, 50, 75, 100, 150, 200]):
    """
    異なるクラスタ数で評価
    """
    results = {
        'k': [],
        'inertia': [],
        'silhouette': [],
        'davies_bouldin': []
    }

    for k in k_values:
        print(f"\nK={k} を評価中...")

        # クラスタリング
        kmeans = MiniBatchKMeans(
            n_clusters=k,
            batch_size=4096,
            max_iter=200,
            n_init=3,
            random_state=0,
            verbose=0
        )
        labels = kmeans.fit_predict(X)

        # イナーシャ（クラスタ内距離の総和）
        inertia = kmeans.inertia_

        # シルエット係数（-1〜1、高いほど良い）
        # サンプルサイズが大きいと重いので、さらにサンプリング
        sample_idx = np.random.choice(len(X), min(10000, len(X)), replace=False)
        silhouette = silhouette_score(X[sample_idx], labels[sample_idx])

        # Davies-Bouldin指数（低いほど良い）
        db_score = davies_bouldin_score(X, labels)

        results['k'].append(k)
        results['inertia'].append(inertia)
        results['silhouette'].append(silhouette)
        results['davies_bouldin'].append(db_score)

        print(f"  イナーシャ: {inertia:.2f}")
        print(f"  シルエット係数: {silhouette:.4f}")
        print(f"  Davies-Bouldin指数: {db_score:.4f}")

    return results

def plot_results(results):
    """
    結果をプロット
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # エルボー法
    axes[0].plot(results['k'], results['inertia'], 'bo-')
    axes[0].set_xlabel('クラスタ数 K')
    axes[0].set_ylabel('イナーシャ（低いほど良い）')
    axes[0].set_title('エルボー法')
    axes[0].grid(True)
    axes[0].axvline(x=90, color='r', linestyle='--', label='現在のK=90')
    axes[0].legend()

    # シルエット係数
    axes[1].plot(results['k'], results['silhouette'], 'go-')
    axes[1].set_xlabel('クラスタ数 K')
    axes[1].set_ylabel('シルエット係数（高いほど良い）')
    axes[1].set_title('シルエット係数')
    axes[1].grid(True)
    axes[1].axvline(x=90, color='r', linestyle='--', label='現在のK=90')
    axes[1].legend()

    # Davies-Bouldin指数
    axes[2].plot(results['k'], results['davies_bouldin'], 'ro-')
    axes[2].set_xlabel('クラスタ数 K')
    axes[2].set_ylabel('Davies-Bouldin指数（低いほど良い）')
    axes[2].set_title('Davies-Bouldin指数')
    axes[2].grid(True)
    axes[2].axvline(x=90, color='r', linestyle='--', label='現在のK=90')
    axes[2].legend()

    plt.tight_layout()
    plt.savefig(Path(__file__).resolve().parent / 'cluster_evaluation.png', dpi=100)
    print("\nグラフ保存: cluster_evaluation.png")

def print_recommendation(results):
    """
    推奨クラスタ数を提示
    """
    print("\n" + "=" * 60)
    print("評価結果サマリー")
    print("=" * 60)

    # シルエット係数が最大のK
    best_silhouette_idx = np.argmax(results['silhouette'])
    best_k_silhouette = results['k'][best_silhouette_idx]

    # Davies-Bouldin指数が最小のK
    best_db_idx = np.argmin(results['davies_bouldin'])
    best_k_db = results['k'][best_db_idx]

    print(f"\n最高シルエット係数: K={best_k_silhouette} (スコア: {results['silhouette'][best_silhouette_idx]:.4f})")
    print(f"最低Davies-Bouldin: K={best_k_db} (スコア: {results['davies_bouldin'][best_db_idx]:.4f})")

    # 現在のK=90の評価
    if 90 in results['k']:
        idx_90 = results['k'].index(90)
        print(f"\n現在のK=90:")
        print(f"  シルエット係数: {results['silhouette'][idx_90]:.4f}")
        print(f"  Davies-Bouldin: {results['davies_bouldin'][idx_90]:.4f}")

    print("\n推奨:")
    print("  - シルエット係数が高い → クラスタが明確に分離")
    print("  - Davies-Bouldin指数が低い → クラスタ間が離れている")
    print("  - エルボー法で「肘」が見えるポイントが最適")
    print("=" * 60)

if __name__ == "__main__":
    # サンプルデータ読み込み
    X = load_sample_vectors(sample_size=50000)

    # 評価実行（50以下を重点的に）
    k_values = [10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90]
    results = evaluate_clusters(X, k_values)

    # 結果表示
    print_recommendation(results)

    # グラフ保存
    plot_results(results)

    print("\n完了！cluster_evaluation.png を確認してください。")
