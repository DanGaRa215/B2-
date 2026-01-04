#!/usr/bin/env python3
"""
ベクトルの正規化状態を確認
"""
import psycopg2
import numpy as np

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# サンプルのレビューベクトルを取得
cur.execute("""
    SELECT review_id, feature_vector
    FROM review_vectors
    LIMIT 10
""")

print("レビューベクトルの正規化状態を確認:")
print("=" * 60)

for review_id, vec in cur.fetchall():
    vec_np = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(vec_np)

    print(f"review_id={review_id}: ノルム={norm:.6f}")

    if abs(norm - 1.0) > 0.01:
        print(f"  ⚠️ 正規化されていない！（ノルム != 1.0）")
    else:
        print(f"  ✓ 正規化済み")

conn.close()

print("\n" + "=" * 60)
print("結論:")
print("  もしノルムが1.0でない場合、レビューベクトルが")
print("  L2正規化されていないことが原因です。")
