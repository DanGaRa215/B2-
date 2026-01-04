#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# 中心ベクトルテーブルの内容を確認
cur.execute("SELECT cluster_id FROM cluster_centroids ORDER BY cluster_id;")
cluster_ids = [row[0] for row in cur.fetchall()]

print(f"cluster_centroids テーブル:")
print(f"  総クラスタ数: {len(cluster_ids)}")
print(f"  クラスタID範囲: {min(cluster_ids)} ~ {max(cluster_ids)}")

# review_clustersのクラスタIDを確認
cur.execute("SELECT DISTINCT cluster_id FROM review_clusters ORDER BY cluster_id;")
assigned_cluster_ids = [row[0] for row in cur.fetchall()]

print(f"\nreview_clusters テーブル:")
print(f"  使用されているクラスタ数: {len(assigned_cluster_ids)}")
print(f"  クラスタID範囲: {min(assigned_cluster_ids)} ~ {max(assigned_cluster_ids)}")

conn.close()
