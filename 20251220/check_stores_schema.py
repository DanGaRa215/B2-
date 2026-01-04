#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# storesテーブルのカラム情報を取得
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'stores'
    ORDER BY ordinal_position;
""")

print("=== stores テーブルのカラム ===")
for col_name, data_type in cur.fetchall():
    print(f"  {col_name}: {data_type}")

# サンプルデータも表示
print("\n=== サンプルデータ（1件） ===")
cur.execute("SELECT * FROM stores LIMIT 1;")
row = cur.fetchone()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'stores' ORDER BY ordinal_position;")
cols = [c[0] for c in cur.fetchall()]

for col, val in zip(cols, row):
    print(f"  {col}: {val}")

conn.close()
