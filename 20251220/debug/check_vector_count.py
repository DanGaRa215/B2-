import psycopg2

conn = psycopg2.connect(host="localhost", database="tabelog_db", user="dangararara")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM store_vectors;")
count = cur.fetchone()[0]

print(f"現在のベクトル数: {count} / 9733店舗")
print(f"進捗: {count/9733*100:.1f}%")

conn.close()
