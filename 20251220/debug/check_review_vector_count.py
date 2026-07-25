import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

# レビューベクトル数を確認
try:
    cur.execute("SELECT COUNT(*) FROM review_vectors;")
    review_count = cur.fetchone()[0]

    # 全レビュー数を取得
    cur.execute("SELECT COUNT(*) FROM reviews WHERE review_text IS NOT NULL AND review_text != '';")
    total_reviews = cur.fetchone()[0]

    progress_pct = review_count / total_reviews * 100 if total_reviews > 0 else 0

    print(f"レビューベクトル数: {review_count:,} / {total_reviews:,}")
    print(f"進捗: {progress_pct:.1f}%")
except Exception as e:
    print(f"エラー: {e}")

conn.close()
