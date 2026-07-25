import psycopg2
import pandas as pd

def check_database(db_name='tabelog_db', user='dangararara'):
    """
    データベースの内容を簡易的に確認するスクリプト
    """
    try:
        conn = psycopg2.connect(
            host="localhost",
            database=db_name,
            user=user
        )
        
        # pandasの表示設定（見やすくするため）
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.max_colwidth', 50)
        pd.set_option('display.unicode.east_asian_width', True)

        print("\n" + "="*80)
        print("【店舗データ (stores) - 先頭5件】")
        print("="*80)
        df_stores = pd.read_sql("SELECT store_id, store_name, genre, overall_rating FROM stores LIMIT 5", conn)
        print(df_stores)

        print("\n" + "="*80)
        print("【レビューデータ (reviews) - 先頭5件】")
        print("="*80)
        df_reviews = pd.read_sql("SELECT review_id, store_id, review_date, left(review_text, 30) as review_text_preview FROM reviews LIMIT 5", conn)
        print(df_reviews)

        print("\n" + "="*80)
        print("【レビュー数が多い店舗トップ5】")
        print("="*80)
        query_ranking = """
        SELECT s.store_name, COUNT(r.review_id) as review_count, s.overall_rating
        FROM stores s
        JOIN reviews r ON s.store_id = r.store_id
        GROUP BY s.store_id, s.store_name, s.overall_rating
        ORDER BY review_count DESC
        LIMIT 5
        """
        df_ranking = pd.read_sql(query_ranking, conn)
        print(df_ranking)
        print("\n")

    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    check_database()
