"""
CSVファイルをPostgreSQLにインポートするスクリプト
"""
import psycopg2
import pandas as pd
from datetime import datetime

def import_csv_to_postgres(csv_file, db_name='tabelog_db', user='dangararara'):
    """
    CSVファイルをPostgreSQLにインポート
    """
    print("="*70)
    print("CSVデータをPostgreSQLにインポート")
    print("="*70)

    # データベース接続
    try:
        conn = psycopg2.connect(
            host="localhost",
            database=db_name,
            user=user
        )
        cur = conn.cursor()
        print(f"\n✓ データベース接続成功: {db_name}")
    except Exception as e:
        print(f"\n✗ データベース接続エラー: {e}")
        return

    try:
        # CSVを読み込み
        print(f"\nCSV読み込み中: {csv_file}")
        df = pd.read_csv(csv_file, encoding='utf-8')
        print(f"✓ CSV読み込み完了: {len(df)} 行")

        # ヘルパー関数: 安全にfloatに変換
        def safe_float(value):
            if pd.isna(value) or str(value).strip() == '-':
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        # 店舗データを抽出（重複削除）
        stores_df = df[['店舗ID', '店舗名', 'ジャンル', '総合評価', '店舗URL']].drop_duplicates(subset=['店舗ID'])
        print(f"\n店舗数: {len(stores_df)} 件")

        # 店舗データをINSERT
        print("\n店舗データをINSERT中...")
        store_count = 0
        for idx, row in stores_df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO stores (store_id, store_name, genre, overall_rating, store_url)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (store_id) DO UPDATE SET
                        store_name = EXCLUDED.store_name,
                        genre = EXCLUDED.genre,
                        overall_rating = EXCLUDED.overall_rating,
                        store_url = EXCLUDED.store_url,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    row['店舗ID'],
                    row['店舗名'],
                    row['ジャンル'] if pd.notna(row['ジャンル']) else None,
                    safe_float(row['総合評価']),
                    row['店舗URL']
                ))
                store_count += 1
                if store_count % 100 == 0:
                    print(f"  {store_count}/{len(stores_df)} 件処理済み")
            except Exception as e:
                print(f"  エラー: {row['店舗ID']} - {e}")
                continue

        conn.commit()
        print(f"✓ 店舗データINSERT完了: {store_count} 件")

        # レビューデータをINSERT
        print(f"\nレビューデータをINSERT中...")
        review_count = 0
        error_count = 0
        for idx, row in df.iterrows():
            # レビュー本文が空の行はスキップ
            if pd.isna(row['レビュー本文']) or str(row['レビュー本文']).strip() == '':
                continue

            try:
                # 日付をパース（"2025/08訪問\n1\n回目" → "2025-08-01"）
                review_date = None
                if pd.notna(row['レビュー日付']):
                    date_str = str(row['レビュー日付']).split('訪問')[0].strip()
                    # "2025/08" → "2025-08-01"
                    if '/' in date_str:
                        parts = date_str.split('/')
                        if len(parts) >= 2:
                            year = parts[0]
                            month = parts[1]
                            review_date = f"{year}-{month.zfill(2)}-01"

                cur.execute("""
                    INSERT INTO reviews (store_id, review_rating, review_date, review_text)
                    VALUES (%s, %s, %s, %s)
                """, (
                    row['店舗ID'],
                    safe_float(row['レビュー評価']),
                    review_date,
                    row['レビュー本文']
                ))
                review_count += 1
                if review_count % 1000 == 0:
                    print(f"  {review_count} 件処理済み")
            except Exception as e:
                error_count += 1
                # 最初の10個のエラーだけ表示
                if error_count <= 10:
                    print(f"  ✗ エラー (行 {idx}): {e}")
                continue

        conn.commit()
        print(f"✓ レビューデータINSERT完了: {review_count} 件 (エラー: {error_count} 件)")

        # 結果確認
        cur.execute("SELECT COUNT(*) FROM stores")
        total_stores = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM reviews")
        total_reviews = cur.fetchone()[0]

        print(f"\n{'='*70}")
        print("インポート完了!")
        print(f"{'='*70}")
        print(f"店舗: {total_stores} 件")
        print(f"レビュー: {total_reviews} 件")
        print(f"{'='*70}")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ エラー: {e}")
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    # CSVファイルをインポート
    import_csv_to_postgres('/Users/dangararara/lecture/miraisouzou/20251220/tabelog_tokyo_all.csv')
