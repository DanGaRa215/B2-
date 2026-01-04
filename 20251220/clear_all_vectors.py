#!/usr/bin/env python
"""store_vectorsとreview_vectorsテーブルのデータを全削除"""
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# store_vectorsの削除前の件数を確認
cur.execute("SELECT COUNT(*) FROM store_vectors;")
store_count = cur.fetchone()[0]
print(f"削除前のstore_vectors: {store_count} 件")

# review_vectorsの削除前の件数を確認
try:
    cur.execute("SELECT COUNT(*) FROM review_vectors;")
    review_count = cur.fetchone()[0]
    print(f"削除前のreview_vectors: {review_count:,} 件")
except:
    review_count = 0
    print("review_vectorsテーブルは存在しないか空です")
    conn.rollback()

# store_vectorsを全削除
cur.execute("DELETE FROM store_vectors;")
print("✓ store_vectorsを削除")

# review_vectorsを全削除（存在する場合）
try:
    cur.execute("DELETE FROM review_vectors;")
    print("✓ review_vectorsを削除")
except:
    conn.rollback()

conn.commit()

# 削除後の確認
cur.execute("SELECT COUNT(*) FROM store_vectors;")
store_after = cur.fetchone()[0]
print(f"\n削除後のstore_vectors: {store_after} 件")

try:
    cur.execute("SELECT COUNT(*) FROM review_vectors;")
    review_after = cur.fetchone()[0]
    print(f"削除後のreview_vectors: {review_after} 件")
except:
    pass

print(f"\n✓ 完了: store_vectors {store_count}件、review_vectors {review_count:,}件を削除しました")

conn.close()
