#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# 古いクラスタ中心（cluster_id >= 50）を削除
print("古いクラスタ中心を削除中...")
cur.execute("DELETE FROM cluster_centroids WHERE cluster_id >= 50;")
deleted = cur.rowcount

conn.commit()
print(f"削除完了: {deleted} 件")

# 確認
cur.execute("SELECT COUNT(*) FROM cluster_centroids;")
remaining = cur.fetchone()[0]
print(f"残りのクラスタ数: {remaining}")

conn.close()
