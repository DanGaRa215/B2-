#!/usr/bin/env python
"""store_vectorsテーブルのデータを全削除"""
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# 削除前の件数を確認
cur.execute("SELECT COUNT(*) FROM store_vectors;")
before_count = cur.fetchone()[0]
print(f"削除前のベクトル数: {before_count}")

# 全削除
cur.execute("DELETE FROM store_vectors;")
conn.commit()

# 削除後の件数を確認
cur.execute("SELECT COUNT(*) FROM store_vectors;")
after_count = cur.fetchone()[0]
print(f"削除後のベクトル数: {after_count}")

print(f"✓ {before_count} 件のベクトルを削除しました")

conn.close()
