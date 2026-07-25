"""
CSVファイルをPostgreSQLにインポート（デバッグ版）
"""
import psycopg2
import pandas as pd

def import_csv_debug():
    # データベース接続
    conn = psycopg2.connect(
        host="localhost",
        database="tabelog_db",
        user="dangararara"
    )
    cur = conn.cursor()

    # CSVを読み込み
    df = pd.read_csv('/Users/dangararara/lecture/miraisouzou/20251220/tabelog_tokyo_all.csv')
    print(f"CSV読み込み: {len(df)} 行")

    # レビューインポートをテスト
    print("\nレビューインポートテスト（最初の5件）:")

    imported = 0
    skipped = 0
    errors = 0

    for idx, row in df.head(5).iterrows():
        # レビュー本文チェック
        if pd.isna(row['レビュー本文']) or row['レビュー本文'] == '':
            print(f"行 {idx}: スキップ（本文なし）")
            skipped += 1
            continue

        try:
            print(f"\n行 {idx}: インポート試行")
            print(f"  店舗ID: {row['店舗ID']}")
            print(f"  評価: {row['レビュー評価']}")
            print(f"  日付: {row['レビュー日付']}")
            print(f"  本文: {row['レビュー本文'][:50]}...")

            cur.execute("""
                INSERT INTO reviews (store_id, review_rating, review_date, review_text)
                VALUES (%s, %s, %s, %s)
            """, (
                row['店舗ID'],
                float(row['レビュー評価']) if pd.notna(row['レビュー評価']) else None,
                row['レビュー日付'] if pd.notna(row['レビュー日付']) else None,
                row['レビュー本文']
            ))
            conn.commit()
            print(f"  ✓ 成功")
            imported += 1

        except Exception as e:
            print(f"  ✗ エラー: {e}")
            errors += 1
            conn.rollback()

    print(f"\n結果:")
    print(f"  成功: {imported}")
    print(f"  スキップ: {skipped}")
    print(f"  エラー: {errors}")

    cur.close()
    conn.close()

if __name__ == '__main__':
    import_csv_debug()
