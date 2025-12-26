import psycopg2

def drop_column(db_name='tabelog_db', user='dangararara'):
    try:
        conn = psycopg2.connect(
            host="localhost",
            database=db_name,
            user=user
        )
        cur = conn.cursor()
        
        print("reviewsテーブルからreview_ratingカラムを削除します...")
        # カラムが存在するか確認してから削除（エラー回避のため）
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                           WHERE table_name='reviews' AND column_name='review_rating') THEN
                    ALTER TABLE reviews DROP COLUMN review_rating;
                    RAISE NOTICE 'review_rating column dropped.';
                ELSE
                    RAISE NOTICE 'review_rating column does not exist.';
                END IF;
            END $$;
        """)
        conn.commit()
        print("処理が完了しました。")
        
    except Exception as e:
        conn.rollback()
        print(f"エラー: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    drop_column()
