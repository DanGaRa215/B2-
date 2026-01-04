#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# クラスタ数を確認
cur.execute("SELECT COUNT(DISTINCT cluster_id) FROM cluster_centroids;")
num_clusters = cur.fetchone()[0]

# レビュー割り当て数を確認
cur.execute("SELECT COUNT(*) FROM review_clusters;")
num_assignments = cur.fetchone()[0]

# クラスタごとのレビュー数
cur.execute("""
    SELECT cluster_id, COUNT(*) as count
    FROM review_clusters
    GROUP BY cluster_id
    ORDER BY cluster_id;
""")

print(f"=== クラスタリング状態 ===")
print(f"クラスタ数: {num_clusters} 個")
print(f"割り当て済みレビュー: {num_assignments:,} 件")
print(f"\nクラスタごとのレビュー数:")
for cluster_id, count in cur.fetchall():
    print(f"  cluster_{cluster_id}: {count:,} 件")

conn.close()
