#!/usr/bin/env python3
"""
全CSVファイルをPostgreSQLにバッチインポートするスクリプト
既存データはスキップし、新規データのみ追加
"""
import psycopg2
import pandas as pd
from pathlib import Path
import sys

# データベース設定
DB_CONFIG = {
    'host': 'localhost',
    'database': 'tabelog_db',
    'user': 'dangararara'
}

# CSVディレクトリ（20251220/pipeline/02_import/ から見て 20251220/data/）
CSV_DIR = Path(__file__).resolve().parents[2] / 'data'

def safe_float(value):
    """安全にfloatに変換"""
    if pd.isna(value) or str(value).strip() == '-':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def parse_review_date(date_str):
    """レビュー日付をパース"""
    if pd.isna(date_str):
        return None
    try:
        date_str = str(date_str).split('訪問')[0].strip()
        if '/' in date_str:
            parts = date_str.split('/')
            if len(parts) >= 2:
                year = parts[0]
                month = parts[1]
                return f"{year}-{month.zfill(2)}-01"
    except Exception:
        pass
    return None

def import_csv_file(csv_path, conn):
    """1つのCSVファイルをインポート"""
    print(f"\n{'='*70}")
    print(f"処理中: {csv_path.name}")
    print(f"{'='*70}")

    try:
        # CSV読み込み
        print("CSV読み込み中...")
        df = pd.read_csv(csv_path, encoding='utf-8')
        print(f"✓ {len(df):,} 行読み込み完了")

        cur = conn.cursor()

        # 店舗データ処理
        stores_df = df[['店舗ID', '店舗名', 'ジャンル', '総合評価', '店舗URL']].drop_duplicates(subset=['店舗ID'])
        print(f"\n店舗データ処理中: {len(stores_df):,} 件")

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
                        store_url = EXCLUDED.store_url
                """, (
                    row['店舗ID'],
                    row['店舗名'],
                    row['ジャンル'] if pd.notna(row['ジャンル']) else None,
                    safe_float(row['総合評価']),
                    row['店舗URL']
                ))
                store_count += 1
                if store_count % 500 == 0:
                    print(f"  店舗: {store_count:,}/{len(stores_df):,}")
                    conn.commit()
            except Exception as e:
                print(f"  ⚠️ 店舗エラー ({row['店舗ID']}): {e}")
                continue

        conn.commit()
        print(f"✓ 店舗データ完了: {store_count:,} 件")

        # レビューデータ処理（バッチINSERT）
        print(f"\nレビューデータ処理中...")
        review_count = 0
        error_count = 0
        batch = []
        batch_size = 5000

        for idx, row in df.iterrows():
            # 10文字未満のレビューはスキップ。
            # '？' や '美味しかった' のような短い本文は SimCSE が意味の薄い
            # ベクトルを生成し、どのクエリにも弱く一致するノイズになる。
            text = '' if pd.isna(row['レビュー本文']) else str(row['レビュー本文']).strip()
            if len(text) < 10:
                continue

            review_date = parse_review_date(row.get('レビュー日付'))

            batch.append((
                row['店舗ID'],
                safe_float(row['レビュー評価']),
                review_date,
                text
            ))

            # バッチが溜まったらINSERT
            if len(batch) >= batch_size:
                try:
                    cur.executemany("""
                        INSERT INTO reviews (store_id, review_rating, review_date, review_text)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (store_id, md5(review_text)) DO NOTHING
                    """, batch)
                    review_count += len(batch)
                    conn.commit()
                    print(f"  レビュー: {review_count:,} 件処理済み")
                    batch = []
                except Exception as e:
                    error_count += len(batch)
                    print(f"  ⚠️ バッチエラー: {e}")
                    conn.rollback()
                    batch = []

        # 残りのバッチを処理
        if batch:
            try:
                cur.executemany("""
                    INSERT INTO reviews (store_id, review_rating, review_date, review_text)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, batch)
                review_count += len(batch)
                conn.commit()
            except Exception as e:
                error_count += len(batch)
                print(f"  ⚠️ 最終バッチエラー: {e}")
                conn.rollback()

        print(f"✓ レビューデータ完了: {review_count:,} 件 (エラー: {error_count} 件)")

        cur.close()
        return True

    except Exception as e:
        print(f"❌ ファイル処理エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """メイン処理"""
    print("="*70)
    print("全CSVファイルのバッチインポート")
    print("="*70)

    # CSVファイル一覧を取得
    csv_files = sorted(CSV_DIR.glob('*.csv'))
    print(f"\n検出されたCSVファイル: {len(csv_files)} 件")
    for f in csv_files:
        print(f"  - {f.name}")

    # データベース接続
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"\n✓ データベース接続成功")
    except Exception as e:
        print(f"\n❌ データベース接続エラー: {e}")
        sys.exit(1)

    try:
        # 処理前の件数確認
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stores")
        before_stores = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM reviews")
        before_reviews = cur.fetchone()[0]
        cur.close()

        print(f"\n処理前:")
        print(f"  店舗: {before_stores:,} 件")
        print(f"  レビュー: {before_reviews:,} 件")

        # 各CSVファイルをインポート
        success_count = 0
        for csv_file in csv_files:
            if import_csv_file(csv_file, conn):
                success_count += 1

        # 処理後の件数確認
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stores")
        after_stores = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM reviews")
        after_reviews = cur.fetchone()[0]
        cur.close()

        print(f"\n{'='*70}")
        print("インポート完了!")
        print(f"{'='*70}")
        print(f"処理ファイル数: {success_count}/{len(csv_files)}")
        print(f"\n処理後:")
        print(f"  店舗: {after_stores:,} 件 (+{after_stores - before_stores:,})")
        print(f"  レビュー: {after_reviews:,} 件 (+{after_reviews - before_reviews:,})")
        print(f"{'='*70}")

    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
