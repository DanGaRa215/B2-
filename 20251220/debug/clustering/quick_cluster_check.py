#!/usr/bin/env python3
"""
現在のクラスタの品質を簡易チェック
"""
import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# クラスタごとのレビュー数の分布
cur.execute("""
    SELECT cluster_id, COUNT(*) as count
    FROM review_clusters
    GROUP BY cluster_id
    ORDER BY count DESC
""")

counts = [row[1] for row in cur.fetchall()]

import numpy as np

print("=== クラスタサイズの統計 ===")
print(f"平均: {np.mean(counts):.0f} 件")
print(f"中央値: {np.median(counts):.0f} 件")
print(f"標準偏差: {np.std(counts):.0f} 件")
print(f"最大: {np.max(counts):,} 件")
print(f"最小: {np.min(counts):,} 件")
print(f"最大/最小比: {np.max(counts)/np.min(counts):.1f}x")

print("\n=== 評価 ===")
ratio = np.max(counts) / np.min(counts)
if ratio > 10:
    print("⚠️ クラスタサイズの偏りが大きい（最大/最小 > 10倍）")
    print("   → クラスタ数を増やすことを検討")
elif ratio > 5:
    print("⚠️ やや偏りがある（最大/最小 > 5倍）")
else:
    print("✓ クラスタサイズが比較的均等")

avg_size = np.mean(counts)
if avg_size > 20000:
    print(f"⚠️ 平均クラスタサイズが大きい（{avg_size:.0f}件）")
    print("   → 検索効率のためクラスタ数を増やすことを検討")
elif avg_size > 10000:
    print(f"△ 平均クラスタサイズがやや大きい（{avg_size:.0f}件）")
else:
    print(f"✓ 平均クラスタサイズが適切（{avg_size:.0f}件）")

conn.close()
