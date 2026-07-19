#!/usr/bin/env python
"""ベクトル生成スクリプト v6 - レビューごとベクトル化版"""

# 重要: 他のインポートより前に環境変数を設定
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import psycopg2
import sys
import fcntl
from sentence_transformers import SentenceTransformer

# モデル設定
MODEL_NAME = 'pkshatech/simcse-ja-bert-base-clcmlp'

print("=== ベクトル生成スクリプト v6 (レビューごとベクトル化版) ===")
print(f"OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS')}")
print(f"モデル: {MODEL_NAME}")

def generate_vectors(db_name='tabelog_db', user='dangararara'):
    # プロセスロック
    lock_file = '/tmp/generate_store_vectors.lock'
    lock_fp = open(lock_file, 'w')
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("✓ プロセスロックを取得しました")
    except IOError:
        print("❌ エラー: 既に別のプロセスが実行中です")
        sys.exit(1)

    # モデルロード
    print("モデルをロード中...")

    # GPU（MPS）モードを使用
    import torch
    if torch.backends.mps.is_available():
        device = 'mps'
        print(f"✓ デバイス: {device} (Apple Silicon GPU)")
    else:
        device = 'cpu'
        print(f"✓ デバイス: {device} (CPUモード)")

    try:
        model = SentenceTransformer(MODEL_NAME, device=device)
        model.max_seq_length = 512
        print(f"✓ モデルロード完了 (device: {device})")
    except Exception as e:
        print(f"❌ モデルロードエラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # DB接続
    conn = None
    try:
        conn = psycopg2.connect(host="localhost", database=db_name, user=user)
        cur = conn.cursor()

        # 全レビュー数を取得
        print("レビュー数を確認中...")
        cur.execute("SELECT COUNT(*) FROM reviews")
        total_reviews = cur.fetchone()[0]
        print(f"全レビュー数: {total_reviews:,} 件")

        # レビューベクトルを保存するための一時テーブルを作成
        print("テーブルを確認中...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS review_vectors (
                review_id INTEGER PRIMARY KEY,
                store_id INTEGER NOT NULL,
                feature_vector FLOAT[] NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # インデックス作成はスキップ（後で手動で作成可能）
        # cur.execute("CREATE INDEX IF NOT EXISTS idx_review_vectors_store_id ON review_vectors(store_id)")
        print("✓ テーブル確認完了")

        # 既に処理済みのレビュー数を確認（COUNTは遅いのでスキップ）
        # cur.execute("SELECT COUNT(*) FROM review_vectors")
        # already_processed = cur.fetchone()[0]
        already_processed = 0  # 簡略化のため0に設定
        print(f"処理済みカウントはスキップ（進捗表示は未処理分のみ表示）")

        # 未処理のレビューデータのみを取得（review_id, review_text, store_id）
        # LEFT JOINで高速化（NOT INより数十倍高速）
        print("未処理のレビューデータを取得中...")
        query = """
        SELECT r.review_id, r.review_text, r.store_id
        FROM reviews r
        LEFT JOIN review_vectors rv ON r.review_id = rv.review_id
        WHERE r.review_text IS NOT NULL AND r.review_text != ''
          AND rv.review_id IS NULL
        ORDER BY r.review_id
        """
        cur.execute(query)
        all_reviews = cur.fetchall()  # 先に全て取得
        print(f"未処理レビュー数: {len(all_reviews):,} 件")

        if len(all_reviews) == 0:
            print("✓ 全てのレビューが既に処理済みです")
            return

        # バッチ処理でレビューをベクトル化
        print("レビューのベクトル化を開始します...")
        batch_size = 64  # レビューは短いのでバッチサイズを大きくできる
        review_batch = []
        review_ids_batch = []
        store_ids_batch = []
        processed_count = 0

        for row in all_reviews:
            review_id, review_text, store_id = row

            review_batch.append(review_text)
            review_ids_batch.append(review_id)
            store_ids_batch.append(store_id)

            # バッチが溜まったら処理
            if len(review_batch) >= batch_size:
                try:
                    # バッチでベクトル化
                    vectors = model.encode(
                        review_batch,
                        batch_size=batch_size,
                        show_progress_bar=False,
                        convert_to_numpy=True
                    )

                    # DBに保存
                    for rev_id, st_id, vec in zip(review_ids_batch, store_ids_batch, vectors):
                        cur.execute("""
                            INSERT INTO review_vectors (review_id, store_id, feature_vector)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (review_id) DO UPDATE SET
                                feature_vector = EXCLUDED.feature_vector,
                                created_at = CURRENT_TIMESTAMP
                        """, (int(rev_id), int(st_id), vec.tolist()))

                    conn.commit()
                    processed_count += len(review_batch)

                    # 進捗表示（1000件ごと）
                    if processed_count % 1000 == 0 or processed_count == len(review_batch):
                        progress_pct = processed_count / len(all_reviews) * 100
                        total_with_existing = already_processed + processed_count
                        overall_pct = total_with_existing / total_reviews * 100
                        # プログレスバー風表示
                        bar_length = 40
                        filled = int(bar_length * progress_pct / 100)
                        bar = '█' * filled + '░' * (bar_length - filled)
                        print(f"  [{bar}] {progress_pct:.1f}% | 処理: {processed_count:,}/{len(all_reviews):,} | 全体: {total_with_existing:,}/{total_reviews:,} ({overall_pct:.1f}%)")

                except Exception as e:
                    print(f"  ⚠️  バッチ処理エラー: {e}")
                    conn.rollback()

                # バッチをクリア
                review_batch = []
                review_ids_batch = []
                store_ids_batch = []

        # 残りのレビューを処理
        if review_batch:
            try:
                vectors = model.encode(
                    review_batch,
                    batch_size=len(review_batch),
                    show_progress_bar=False,
                    convert_to_numpy=True
                )

                for rev_id, st_id, vec in zip(review_ids_batch, store_ids_batch, vectors):
                    cur.execute("""
                        INSERT INTO review_vectors (review_id, store_id, feature_vector)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (review_id) DO UPDATE SET
                            feature_vector = EXCLUDED.feature_vector,
                            created_at = CURRENT_TIMESTAMP
                    """, (int(rev_id), int(st_id), vec.tolist()))

                conn.commit()
                processed_count += len(review_batch)
            except Exception as e:
                print(f"  ⚠️  最終バッチエラー: {e}")
                conn.rollback()

        print(f"\n✓ レビューベクトル化完了: {processed_count:,} 件")
        print("✓ review_vectorsテーブルにレビューベクトルを保存しました")
        print("  (店舗ごとの平均化はスキップします)")

    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
        if 'lock_fp' in locals():
            fcntl.flock(ock_fp.fileno(), fcntl.LOCK_UN)
            lock_fp.close()
            print("✓ プロセスロックを解放しました")

if __name__ == "__main__":
    generate_vectors()
