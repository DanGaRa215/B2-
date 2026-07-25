#!/usr/bin/env python3
"""
クラスタ数(K)・探索クラスタ数(TOP_K_CLUSTERS)をタスクベースで評価する。

evaluate_cluster_number.py はクラスタの幾何学的な分離度(シルエット係数・
Davies-Bouldin指数・エルボー法)を見ているが、K=10〜90のどの値でもスコアが
ほぼ横ばいで、K の妥当性を判断する材料になっていない(README.md の
「既知の性質」参照)。

recommend.py のクラスタ絞り込みは、実質的に近似最近傍探索(ANN)の IVF
インデックスとして機能している(クエリに近い重心のクラスタだけを見ることで
全レビューを舐めずに済ませる)。そこで本スクリプトは IVF の標準的な
チューニング手法にならい、ブルートフォース(全件探索)を ground truth として、
(クラスタ数 K, 見るクラスタ数 nprobe) の組み合わせごとに
recall(取りこぼしのなさ) と selectivity(絞り込みの効き) のトレードオフを
実測する。

★ このスクリプトは調査・評価専用であり、review_clusters / cluster_centroids
  など production テーブルへの書き込みは一切行わない(SELECT のみ)。
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import csv
from pathlib import Path

import numpy as np
import psycopg2
import torch
from sentence_transformers import SentenceTransformer
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import normalize
import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams["font.family"] = "Hiragino Sans"

DB_HOST = "localhost"
DB_NAME = "tabelog_db"
DB_USER = "dangararara"

MODEL_NAME = "pkshatech/simcse-ja-bert-base-clcmlp"

# recommend.py:26 の SHRINKAGE_M と同じ値。ground truth のスコアリングを
# recommend.py:89-120 の calculate_store_similarity と一致させるため。
SHRINKAGE_M = 5

# 35 = 現行値、50 = README_提案手法.md に記載の値。比較用に両方含める。
K_CANDIDATES = [10, 20, 35, 50, 75, 100, 150, 200]
NPROBE_FRACTIONS = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
# recommend.py:20 の TOP_K_CLUSTERS と同じ値。どの K でも必ず比較対象に含める。
CURRENT_TOP_K_CLUSTERS = 10
CURRENT_K = 35

TRAIN_SAMPLE_SIZE = 300_000
KMEANS_N_INIT = 3
KMEANS_MAX_ITER = 100
RANDOM_STATE = 0

RECALL_NS = (10, 20)

TEST_QUERIES = [
    "デートで使える落ち着いた雰囲気の店",
    "気軽にコスパよく友達と行ける",
    "一人でふらっと入れる静かなお店",
    "大人数の宴会に使える個室があるお店",
    "記念日や誕生日のお祝いにぴったりのレストラン",
    "深夜まで営業している一人飲みできる店",
    "子連れでも安心して行けるファミリー向けのお店",
    "がっつり肉が食べたいときのお店",
    "新鮮な魚介や寿司が楽しめるお店",
    "おしゃれなカフェでゆっくりお茶したい",
    "接待に使える高級感のあるお店",
    "安くて量が多いボリューム満点の定食屋",
    "ビールが美味しい昼飲みできる店",
    "女子会にぴったりな映えるお店",
    "ラーメンが美味しい行列のできる店",
    "ワインの種類が豊富なイタリアン",
    "静かに読書しながら過ごせるカフェ",
    "テイクアウトができるお弁当屋",
]

OUT_DIR = Path(__file__).resolve().parent


def connect():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER)


def get_total_store_count(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stores")
    return cur.fetchone()[0]


def load_all_vectors(conn):
    """review_vectors を1回だけ全件ロードする。以降の全 K 候補で使い回す。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM review_vectors
        WHERE feature_vector IS NOT NULL AND store_id IS NOT NULL
    """)
    n = cur.fetchone()[0]
    print(f"[load] {n:,} 件のレビューベクトルを読み込みます...")

    X = np.empty((n, 768), dtype=np.float32)
    store_ids = np.empty(n, dtype=np.int64)

    read_conn = connect()
    read_cur = read_conn.cursor(name="ivf_eval_cursor")
    read_cur.itersize = 5000
    read_cur.execute("""
        SELECT store_id, feature_vector
        FROM review_vectors
        WHERE feature_vector IS NOT NULL AND store_id IS NOT NULL
        ORDER BY review_id
    """)

    offset = 0
    while True:
        rows = read_cur.fetchmany(5000)
        if not rows:
            break
        for i, (sid, vec) in enumerate(rows):
            X[offset + i] = vec
            store_ids[offset + i] = sid
        offset += len(rows)
        if offset % 200_000 < 5000:
            print(f"[load] {offset:,} / {n:,} 件読み込み済み...")
    read_conn.close()

    X = normalize(X, norm="l2", axis=1, copy=False)
    print(f"[load] 完了: X.shape={X.shape}")
    return store_ids, X


def nprobe_candidates(k: int) -> list:
    vals = {max(1, round(k * f)) for f in NPROBE_FRACTIONS}
    vals = {v for v in vals if v <= k}
    vals.add(min(CURRENT_TOP_K_CLUSTERS, k))
    return sorted(vals)


def vectorize_queries(queries: list) -> dict:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[model] {MODEL_NAME} をロード中 (device={device})...")
    model = SentenceTransformer(MODEL_NAME, device=device)
    vecs = model.encode(queries, convert_to_numpy=True, show_progress_bar=False)
    vecs = normalize(vecs.astype(np.float32), norm="l2", axis=1)
    return {q: v for q, v in zip(queries, vecs)}


def build_ground_truth(query_vec, X, store_codes, n_codes):
    """
    recommend.py:89-120 の calculate_store_similarity と同一ロジック。
    alpha (星評価とのハイブリッド) は含めない、純粋な類似度のみのランキング。
    """
    sims = X @ query_vec
    sums = np.bincount(store_codes, weights=sims, minlength=n_codes)
    counts = np.bincount(store_codes, minlength=n_codes)
    raw = sums / counts  # store_codes は review_vectors 由来なので counts は必ず >=1
    prior = raw.mean()
    shrunk = (counts * raw + SHRINKAGE_M * prior) / (counts + SHRINKAGE_M)
    order = np.argsort(-shrunk)
    return order


def fit_kmeans_on_sample(X, k, seed=RANDOM_STATE):
    rng = np.random.default_rng(seed)
    sample_size = min(TRAIN_SAMPLE_SIZE, len(X))
    idx = rng.choice(len(X), size=sample_size, replace=False)
    km = MiniBatchKMeans(
        n_clusters=k,
        batch_size=4096,
        max_iter=KMEANS_MAX_ITER,
        n_init=KMEANS_N_INIT,
        random_state=seed,
    )
    km.fit(X[idx])
    centroids = normalize(km.cluster_centers_.astype(np.float32), norm="l2", axis=1)
    return centroids


def assign_all_chunked(X, centroids, chunk=200_000):
    """
    単位ベクトル同士では「コサイン類似度最大」=「ユークリッド距離最小」なので、
    内積 argmax で MiniBatchKMeans.predict と同等のクラスタ割り当てを行う。
    """
    n = len(X)
    labels = np.empty(n, dtype=np.int32)
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        sims = X[start:end] @ centroids.T
        labels[start:end] = np.argmax(sims, axis=1)
    return labels


def evaluate_combo(store_codes, n_codes, labels, centroids, query_vec,
                    k, nprobe, gt_order, total_stores, recall_ns=RECALL_NS):
    sims_centroid = centroids @ query_vec
    if nprobe < k:
        chosen = np.argpartition(-sims_centroid, nprobe - 1)[:nprobe]
    else:
        chosen = np.arange(k)
    is_chosen = np.zeros(k, dtype=bool)
    is_chosen[chosen] = True
    row_mask = is_chosen[labels]

    sub_codes = store_codes[row_mask]
    counts = np.bincount(sub_codes, minlength=n_codes)
    candidate_codes = np.nonzero(counts > 0)[0]
    candidate_set = set(candidate_codes.tolist())

    selectivity = len(candidate_codes) / total_stores

    result = {"selectivity": selectivity, "candidate_count": len(candidate_codes)}
    for n in recall_ns:
        gt_top_n = set(gt_order[:n].tolist())
        result[f"recall_at_{n}"] = len(gt_top_n & candidate_set) / n
    return result


def summarize(raw_rows):
    groups = {}
    for row in raw_rows:
        key = (row["k"], row["nprobe"])
        groups.setdefault(key, []).append(row)

    summary = []
    for (k, nprobe), rows in sorted(groups.items()):
        recall10 = [r["recall_at_10"] for r in rows]
        recall20 = [r["recall_at_20"] for r in rows]
        summary.append({
            "k": k,
            "nprobe": nprobe,
            "nprobe_ratio": nprobe / k,
            "avg_selectivity": float(np.mean([r["selectivity"] for r in rows])),
            "avg_candidate_count": float(np.mean([r["candidate_count"] for r in rows])),
            "avg_recall_at_10": float(np.mean(recall10)),
            "std_recall_at_10": float(np.std(recall10)),
            "avg_recall_at_20": float(np.mean(recall20)),
        })
    return summary


def write_raw_csv(raw_rows):
    path = OUT_DIR / "ivf_recall_eval_raw.csv"
    fieldnames = ["k", "nprobe", "nprobe_ratio", "query", "selectivity",
                  "candidate_count", "recall_at_10", "recall_at_20"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_rows)
    print(f"[out] {path}")


def write_summary_csv(summary_rows):
    path = OUT_DIR / "ivf_recall_eval_summary.csv"
    fieldnames = ["k", "nprobe", "nprobe_ratio", "avg_selectivity", "avg_candidate_count",
                  "avg_recall_at_10", "std_recall_at_10", "avg_recall_at_20"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"[out] {path}")


def pareto_frontier(summary_rows, recall_key="avg_recall_at_10"):
    rows_sorted = sorted(summary_rows, key=lambda r: r["avg_selectivity"])
    frontier = []
    best_recall = -1.0
    for row in rows_sorted:
        if row[recall_key] > best_recall:
            frontier.append(row)
            best_recall = row[recall_key]
    return frontier


def plot_results(summary_rows):
    ks = sorted(set(r["k"] for r in summary_rows))
    cmap = plt.get_cmap("viridis", len(ks))
    k_color = {k: cmap(i) for i, k in enumerate(ks)}

    fig, axes = plt.subplots(1, 3, figsize=(20, 6))

    # 1) recall@10 vs selectivity のトレードオフ散布図 + パレートフロンティア
    ax = axes[0]
    for k in ks:
        rows = [r for r in summary_rows if r["k"] == k]
        ax.scatter([r["avg_selectivity"] for r in rows],
                   [r["avg_recall_at_10"] for r in rows],
                   color=k_color[k], label=f"K={k}")
        for r in rows:
            ax.annotate(str(r["nprobe"]), (r["avg_selectivity"], r["avg_recall_at_10"]),
                        fontsize=7, alpha=0.7)
    frontier = pareto_frontier(summary_rows)
    ax.plot([r["avg_selectivity"] for r in frontier],
            [r["avg_recall_at_10"] for r in frontier],
            "k--", linewidth=1, label="パレートフロンティア")
    current = next((r for r in summary_rows if r["k"] == CURRENT_K and r["nprobe"] == CURRENT_TOP_K_CLUSTERS), None)
    if current:
        ax.scatter([current["avg_selectivity"]], [current["avg_recall_at_10"]],
                   marker="*", s=300, color="red", zorder=5, label=f"現行 (K={CURRENT_K}, nprobe={CURRENT_TOP_K_CLUSTERS})")
    ax.set_xlabel("selectivity (候補店舗数 / 全店舗数、低いほど絞り込めている)")
    ax.set_ylabel("recall@10 (高いほど良い)")
    ax.set_title("recall vs selectivity トレードオフ")
    ax.legend(fontsize=8)
    ax.grid(True)

    # 2) K ごとの recall@10 - nprobe比率 曲線
    ax = axes[1]
    for k in ks:
        rows = sorted([r for r in summary_rows if r["k"] == k], key=lambda r: r["nprobe_ratio"])
        ax.plot([r["nprobe_ratio"] for r in rows], [r["avg_recall_at_10"] for r in rows],
                "o-", color=k_color[k], label=f"K={k}")
    ax.set_xlabel("nprobe / K (探索するクラスタの割合)")
    ax.set_ylabel("recall@10")
    ax.set_title("K ごとの recall@10")
    ax.legend(fontsize=8)
    ax.grid(True)

    # 3) K ごとの selectivity - nprobe比率 曲線
    ax = axes[2]
    for k in ks:
        rows = sorted([r for r in summary_rows if r["k"] == k], key=lambda r: r["nprobe_ratio"])
        ax.plot([r["nprobe_ratio"] for r in rows], [r["avg_selectivity"] for r in rows],
                "o-", color=k_color[k], label=f"K={k}")
    ax.set_xlabel("nprobe / K (探索するクラスタの割合)")
    ax.set_ylabel("selectivity")
    ax.set_title("K ごとの selectivity")
    ax.legend(fontsize=8)
    ax.grid(True)

    plt.tight_layout()
    out_path = OUT_DIR / "ivf_recall_eval.png"
    plt.savefig(out_path, dpi=100)
    print(f"[out] {out_path}")


def print_recommendation(summary_rows, n_codes, total_stores):
    print("\n" + "=" * 70)
    print("評価結果サマリー")
    print("=" * 70)

    ceiling = n_codes / total_stores
    print(f"\nselectivity の理論上限(レビューを持つ店舗の割合): {ceiling:.3f}")
    print("  ※ レビューが1件も無い店は nprobe をいくら増やしても候補になり得ないため、")
    print("     selectivity=1.0 には到達しない。nprobe=K(全クラスタ探索)の行がこの値に近ければ正常。")

    current = next((r for r in summary_rows if r["k"] == CURRENT_K and r["nprobe"] == CURRENT_TOP_K_CLUSTERS), None)
    if current:
        print(f"\n現行値 (K={CURRENT_K}, nprobe={CURRENT_TOP_K_CLUSTERS}):")
        print(f"  selectivity={current['avg_selectivity']:.3f} (候補店舗 約{current['avg_candidate_count']:.0f}件)")
        print(f"  recall@10={current['avg_recall_at_10']:.3f}, recall@20={current['avg_recall_at_20']:.3f}")

    print("\nパレート最適な (K, nprobe) の組み合わせ (selectivity昇順、recall@10が改善する点のみ):")
    print(f"{'K':>5} {'nprobe':>7} {'比率':>6} {'selectivity':>12} {'recall@10':>10} {'recall@20':>10}")
    for r in pareto_frontier(summary_rows):
        print(f"{r['k']:>5} {r['nprobe']:>7} {r['nprobe_ratio']:>6.0%} "
              f"{r['avg_selectivity']:>12.3f} {r['avg_recall_at_10']:>10.3f} {r['avg_recall_at_20']:>10.3f}")
    print("=" * 70)


def main():
    conn = connect()
    total_stores = get_total_store_count(conn)
    store_ids, X = load_all_vectors(conn)
    conn.close()

    unique_store_ids, store_codes = np.unique(store_ids, return_inverse=True)
    n_codes = len(unique_store_ids)
    print(f"[data] レビューを持つ店舗数: {n_codes:,} / 全店舗数: {total_stores:,}")

    query_vecs = vectorize_queries(TEST_QUERIES)

    print("[gt] ground truth (ブルートフォース) を計算中...")
    gt_orders = {
        q: build_ground_truth(v, X, store_codes, n_codes)
        for q, v in query_vecs.items()
    }

    raw_rows = []
    for k in K_CANDIDATES:
        print(f"\n=== K={k} ===")
        print(f"[fit] {min(TRAIN_SAMPLE_SIZE, len(X)):,} 件のサブサンプルで学習中...")
        centroids = fit_kmeans_on_sample(X, k)
        print("[assign] 全件を割り当て中...")
        labels = assign_all_chunked(X, centroids)

        for nprobe in nprobe_candidates(k):
            combo_rows = []
            for q, qvec in query_vecs.items():
                res = evaluate_combo(
                    store_codes, n_codes, labels, centroids, qvec,
                    k, nprobe, gt_orders[q], total_stores,
                )
                row = {"k": k, "nprobe": nprobe, "nprobe_ratio": nprobe / k, "query": q, **res}
                raw_rows.append(row)
                combo_rows.append(row)
            avg_sel = np.mean([r["selectivity"] for r in combo_rows])
            avg_r10 = np.mean([r["recall_at_10"] for r in combo_rows])
            print(f"  nprobe={nprobe:>4} (比率{nprobe/k:.0%}): "
                  f"selectivity={avg_sel:.3f}, recall@10={avg_r10:.3f}")

    write_raw_csv(raw_rows)
    summary_rows = summarize(raw_rows)
    write_summary_csv(summary_rows)
    plot_results(summary_rows)
    print_recommendation(summary_rows, n_codes, total_stores)


if __name__ == "__main__":
    main()
