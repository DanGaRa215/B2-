import psycopg2
import pandas as pd
import glob
import os
from pathlib import Path
from tqdm import tqdm

def init_database(db_name='tabelog_db', user='dangararara'):
    """
    データベースの初期化
    既存のテーブルを削除して新規作成
    """
    try:
        conn = psycopg2.connect(
            host="localhost",
            database=db_name,
            user=user
        )
        cur = conn.cursor()

        print("既存テーブルを削除中...")
        # 外部キー制約があるため、順番に削除
        cur.execute("DROP TABLE IF EXISTS store_vectors CASCADE;")
        cur.execute("DROP TABLE IF EXISTS reviews CASCADE;")
        cur.execute("DROP TABLE IF EXISTS stores CASCADE;")
        print("削除完了")

        print("新規テーブルを作成中...")
        # storesテーブル作成
        cur.execute("""
            CREATE TABLE stores (
                store_id VARCHAR(50) PRIMARY KEY,
                store_name TEXT NOT NULL,
                genre TEXT,
                overall_rating FLOAT,
                store_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # reviewsテーブル作成
        cur.execute("""
            CREATE TABLE reviews (
                review_id SERIAL PRIMARY KEY,
                store_id VARCHAR(50) NOT NULL,
                reviewer_name TEXT,
                review_rating FLOAT,
                review_date TEXT,
                review_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
            );
        """)

        # インデックス作成
        cur.execute("CREATE INDEX idx_reviews_store_id ON reviews(store_id);")

        conn.commit()
        print("テーブル作成完了")

        return conn, cur

    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        print(f"エラー: {e}")
        raise


def load_csv_data(conn, cur, data_dir=None):
    """
    全CSVファイルをデータベースに投入
    重複店舗は最初に見つかったものを保持
    """
    if data_dir is None:
        # 20251220/pipeline/02_import/ から見て 20251220/data/
        data_dir = Path(__file__).resolve().parents[2] / 'data'
    csv_files = glob.glob(os.path.join(str(data_dir), '*.csv'))
    print(f"\n{len(csv_files)}個のCSVファイルが見つかりました")

    stores_dict = {}  # {store_id: store_info} - 重複排除用
    reviews_list = []

    for csv_file in tqdm(csv_files, desc="CSVファイル読み込み中"):
        try:
            df = pd.read_csv(csv_file, dtype=str)  # 全て文字列として読み込み

            # 列名の正規化（BOMや空白を除去）
            df.columns = df.columns.str.strip().str.replace('\ufeff', '')

            for _, row in df.iterrows():
                store_id = str(row['店舗ID'])

                # 総合評価の処理
                overall_rating = None
                if pd.notna(row['総合評価']) and str(row['総合評価']).strip() not in ['', '-', 'nan']:
                    try:
                        overall_rating = float(row['総合評価'])
                    except:
                        pass

                # 店舗情報を保存（重複の場合は最初のものを保持）
                if store_id not in stores_dict:
                    stores_dict[store_id] = {
                        'store_id': store_id,
                        'store_name': row['店舗名'],
                        'genre': row['ジャンル'],
                        'overall_rating': overall_rating,
                        'store_url': row['店舗URL']
                    }

                # レビューがある場合のみ追加
                if pd.notna(row['レビュー本文']) and str(row['レビュー本文']).strip() != '':
                    # レビュー評価の処理
                    review_rating = None
                    if pd.notna(row['レビュー評価']) and str(row['レビュー評価']).strip() not in ['', '-', 'nan']:
                        try:
                            review_rating = float(row['レビュー評価'])
                        except:
                            pass

                    reviews_list.append({
                        'store_id': store_id,
                        'reviewer_name': row['レビュアー'] if pd.notna(row['レビュアー']) else None,
                        'review_rating': review_rating,
                        'review_date': row['レビュー日付'] if pd.notna(row['レビュー日付']) else None,
                        'review_text': str(row['レビュー本文']).strip()
                    })

        except Exception as e:
            print(f"\nエラー: {csv_file} - {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\n重複排除後: {len(stores_dict)}店舗, {len(reviews_list)}レビュー")

    # データベースに投入
    print("\n店舗データを投入中...")
    for store_info in tqdm(stores_dict.values()):
        cur.execute("""
            INSERT INTO stores (store_id, store_name, genre, overall_rating, store_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (store_id) DO NOTHING
        """, (
            store_info['store_id'],
            store_info['store_name'],
            store_info['genre'],
            store_info['overall_rating'],
            store_info['store_url']
        ))

    conn.commit()
    print("店舗データ投入完了")

    print("\nレビューデータを投入中...")
    batch_size = 1000
    for i in tqdm(range(0, len(reviews_list), batch_size)):
        batch = reviews_list[i:i+batch_size]
        for review in batch:
            cur.execute("""
                INSERT INTO reviews (store_id, reviewer_name, review_rating, review_date, review_text)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                review['store_id'],
                review['reviewer_name'],
                review['review_rating'],
                review['review_date'],
                review['review_text']
            ))
        conn.commit()

    print("レビューデータ投入完了")

    # 統計情報表示
    cur.execute("SELECT COUNT(*) FROM stores;")
    store_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM reviews;")
    review_count = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT s.store_id)
        FROM stores s
        JOIN reviews r ON s.store_id = r.store_id
    """)
    stores_with_reviews = cur.fetchone()[0]

    print(f"\n=== データベース統計 ===")
    print(f"総店舗数: {store_count}")
    print(f"総レビュー数: {review_count}")
    print(f"レビューがある店舗数: {stores_with_reviews}")
    print(f"レビューがない店舗数: {store_count - stores_with_reviews}")


def main():
    try:
        print("=== データベース初期化とデータ投入 ===\n")

        # 初期化
        conn, cur = init_database()

        # データ投入
        load_csv_data(conn, cur)

        print("\n処理完了!")

    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == "__main__":
    main()
