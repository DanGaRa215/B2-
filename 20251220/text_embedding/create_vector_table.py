import psycopg2

def create_vector_table(db_name='tabelog_db', user='dangararara'):
    try:
        conn = psycopg2.connect(
            host="localhost",
            database=db_name,
            user=user
        )
        cur = conn.cursor()
        
        print("store_vectorsテーブルを作成します...")
        cur.execute("""
            DROP TABLE IF EXISTS store_vectors;

            CREATE TABLE store_vectors (
                store_id VARCHAR(50) PRIMARY KEY,
                feature_vector FLOAT8[],
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
            );
        """)
        conn.commit()
        print("テーブル作成完了。")
        
    except Exception as e:
        conn.rollback()
        print(f"エラー: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    create_vector_table()
