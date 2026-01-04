#!/usr/bin/env python3
"""クラスタリング結果を確認するスクリプト"""
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

print("=== クラスタリング結果の確認 ===\n")

# 1. review_clusters テーブル（レビュー → クラスタID の割り当て）
print("1. review_clusters テーブル（レビュー割り当て）")
cur.execute("SELECT COUNT(*) FROM review_clusters;")
total = cur.fetchone()[0]
print(f"   総レビュー数: {total:,} 件\n")

# サンプル表示
print("   サンプル（最初の10件）:")
cur.execute("""
    SELECT review_id, cluster_id
    FROM review_clusters
    ORDER BY review_id
    LIMIT 10;
""")
for row in cur.fetchall():
    print(f"   review_id={row[0]}, cluster_id={row[1]}")

print()

# 2. cluster_centroids テーブル（各クラスタの中心ベクトル）
print("2. cluster_centroids テーブル（クラスタ中心）")
cur.execute("SELECT COUNT(*) FROM cluster_centroids;")
total_clusters = cur.fetchone()[0]
print(f"   総クラスタ数: {total_clusters} 個\n")

# サンプル表示
print("   サンプル（最初の5クラスタ）:")
cur.execute("""
    SELECT cluster_id, array_length(centroid_vector, 1) as dim
    FROM cluster_centroids
    ORDER BY cluster_id
    LIMIT 5;
""")
for row in cur.fetchall():
    print(f"   cluster_id={row[0]}, vector_dim={row[1]}")

print()

# 3. クラスタごとのレビュー数（分布）
print("3. クラスタごとのレビュー数（上位10クラスタ）")
cur.execute("""
    SELECT cluster_id, COUNT(*) as review_count
    FROM review_clusters
    GROUP BY cluster_id
    ORDER BY review_count DESC
    LIMIT 10;
""")
for row in cur.fetchall():
    print(f"   cluster_id={row[0]}: {row[1]:,} 件")

print()

# 4. 実際のレビュー内容を確認（クラスタ0の例）
print("4. クラスタ0に属するレビューの例（5件）")
cur.execute("""
    SELECT r.review_id, r.review_text, rc.cluster_id
    FROM reviews r
    JOIN review_clusters rc ON r.review_id = rc.review_id
    WHERE rc.cluster_id = 0
    LIMIT 5;
""")
for i, row in enumerate(cur.fetchall(), 1):
    text = row[1][:100] + "..." if len(row[1]) > 100 else row[1]
    print(f"   [{i}] review_id={row[0]}, cluster={row[2]}")
    print(f"       {text}\n")

conn.close()
