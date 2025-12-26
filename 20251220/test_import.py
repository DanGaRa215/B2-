"""
簡易テスト: 1件だけインポート
"""
import psycopg2
import pandas as pd

# データベース接続
conn = psycopg2.connect(
    host="localhost",
    database="tabelog_db",
    user="dangararara"
)
cur = conn.cursor()

# CSVを読み込み
df = pd.read_csv('/Users/dangararara/lecture/miraisouzou/20251220/tabelog_tokyo_all.csv')

print(f"総行数: {len(df)}")
print(f"\n最初の1件をインポートテスト:\n")

# 最初の1件
row = df.iloc[0]

print(f"店舗ID: {row['店舗ID']}")
print(f"レビュー本文: {row['レビュー本文'][:100]}...")
print(f"レビュー日付: {row['レビュー日付']}")

# 日付パース
review_date = None
if pd.notna(row['レビュー日付']):
    date_str = str(row['レビュー日付']).split('訪問')[0].strip()
    print(f"日付パース後: {date_str}")
    if '/' in date_str:
        parts = date_str.split('/')
        if len(parts) >= 2:
            year = parts[0]
            month = parts[1]
            review_date = f"{year}-{month.zfill(2)}-01"
            print(f"変換後の日付: {review_date}")

# インポート試行
try:
    cur.execute("""
        INSERT INTO reviews (store_id, review_rating, review_date, review_text)
        VALUES (%s, %s, %s, %s)
    """, (
        row['店舗ID'],
        None,  # 評価はNULL
        review_date,
        row['レビュー本文']
    ))
    conn.commit()
    print("\n✓ インポート成功!")

    # 確認
    cur.execute("SELECT COUNT(*) FROM reviews")
    count = cur.fetchone()[0]
    print(f"レビュー総数: {count}")

except Exception as e:
    print(f"\n✗ エラー: {e}")
    import traceback
    traceback.print_exc()

cur.close()
conn.close()
