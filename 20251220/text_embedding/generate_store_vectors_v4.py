#!/usr/bin/env python
"""ベクトル生成スクリプト v4 - OpenMP競合対策版"""

# 重要: 他のインポートより前に環境変数を設定
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# numpyを最初にインポート（重要）
import numpy as np

import psycopg2
import sys
import fcntl
from sentence_transformers import SentenceTransformer

# モデル設定
MODEL_NAME = 'pkshatech/simcse-ja-bert-base-clcmlp'

print("=== ベクトル生成スクリプト v4 (OpenMP競合対策版) ===")
print(f"OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS')}")
print(f"モデル: {MODEL_NAME}")

def get_long_text_vector(model, text, max_seq_length=512):
    """
    512トークンを超えるテキストをチャンク分割してベクトル化し、平均を取る関数
    """
    if not text:
        return np.zeros(model.get_sentence_embedding_dimension())
        
    # トークナイザの警告(Token indices sequence length is longer than...)を回避
    # 一時的にmodel_max_lengthを大きくして、全テキストをトークン化できるようにする
    original_max_len = model.tokenizer.model_max_length
    model.tokenizer.model_max_length = int(1e9)
    
    try:
        # トークナイズ (return_tensorsを使わずPythonのリストとして取得)
        # add_special_tokens=False にして、後でdecodeしたものを再度encodeする際に付与させる
        inputs = model.tokenizer(text, add_special_tokens=False)
    finally:
        # 設定を戻す
        model.tokenizer.model_max_length = original_max_len

    input_ids = inputs['input_ids']
    
    chunk_size = max_seq_length - 2 # [CLS], [SEP]の分を確保
    total_tokens = len(input_ids)
    
    # 短い場合はそのまま
    if total_tokens <= chunk_size:
        return model.encode(text, convert_to_numpy=True)
        
    # チャンク分割
    chunks = []
    for i in range(0, total_tokens, chunk_size):
        chunk_ids = input_ids[i : i + chunk_size]
        # テキストに復元 (special tokensは含めない)
        chunk_text = model.tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunks.append(chunk_text)
        
    # 各チャンクをベクトル化
    # batch_sizeはチャンク数に合わせて調整
    chunk_vectors = model.encode(chunks, batch_size=len(chunks), show_progress_bar=False, convert_to_numpy=True)
    
    # 平均ベクトルを返す
    return np.mean(chunk_vectors, axis=0)

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

    # デバイス設定（MPS: Apple Silicon GPU）
    import torch
    if torch.backends.mps.is_available():
        device = 'mps'
        print("✓ MPS (Apple Silicon GPU) を使用します")
    else:
        device = 'cpu'
        print("⚠️  MPSが利用できないため、CPUモードで実行します")

    try:
        model = SentenceTransformer(MODEL_NAME, device=device)
        model.max_seq_length = 512  # 明示的に長さを制限
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

        # 既存のベクトル済み店舗IDを取得
        print("既存データを確認中...")
        try:
            cur.execute("SELECT store_id FROM store_vectors")
            existing_ids = set(row[0] for row in cur.fetchall())
            print(f"ベクトル生成済み: {len(existing_ids)} 店舗")
        except:
            existing_ids = set()
            conn.rollback()

        # 処理対象の店舗データを取得
        print("店舗データを取得中...")
        query = """
        SELECT
            s.store_id,
            string_agg(r.review_text, ' ') as combined_text
        FROM stores s
        JOIN reviews r ON s.store_id = r.store_id
        GROUP BY s.store_id
        ORDER BY s.store_id
        """
        cur.execute(query)

        # 未処理の店舗のみフィルタ
        all_stores = []
        for row in cur.fetchall():
            store_id, combined_text = row
            if store_id not in existing_ids:
                all_stores.append((store_id, combined_text))

        total_stores = len(all_stores)
        print(f"今回処理対象: {total_stores} 店舗")

        if total_stores == 0:
            print("全ての店舗のベクトル生成が完了しています。")
            return

        # ベクトル生成と保存
        print("ベクトル生成を開始します...")
        batch_size = 8
        total_batches = (total_stores + batch_size - 1) // batch_size
        print(f"総バッチ数: {total_batches}")

        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total_stores)
            batch_data = all_stores[start_idx:end_idx]

            store_ids = [item[0] for item in batch_data]
            texts = [item[1] for item in batch_data]

            # ベクトル生成
            try:
                vectors = []
                for text in texts:
                    # 長文対応のベクトル生成関数を使用
                    vec = get_long_text_vector(model, text)
                    vectors.append(vec)
                vectors = np.array(vectors)
            except Exception as e:
                print(f"  ⚠️  バッチ {batch_idx + 1} でエラー: {e}")
                continue

            # DBに保存
            for store_id, vector in zip(store_ids, vectors):
                cur.execute("""
                    INSERT INTO store_vectors (store_id, feature_vector)
                    VALUES (%s, %s)
                    ON CONFLICT (store_id) DO UPDATE SET
                        feature_vector = EXCLUDED.feature_vector,
                        created_at = CURRENT_TIMESTAMP
                """, (store_id, vector.tolist()))

            conn.commit()

            # 進捗表示
            if (batch_idx + 1) % 10 == 0 or (batch_idx + 1) == total_batches:
                cur.execute("SELECT COUNT(*) FROM store_vectors")
                current_total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM stores")
                all_stores_count = cur.fetchone()[0]
                progress_pct = current_total / all_stores_count * 100
                print(f"  バッチ {batch_idx + 1}/{total_batches} | 完了: {current_total}/{all_stores_count} ({progress_pct:.1f}%)")

        print(f"\n✓ 完了: {total_stores} 店舗のベクトルを保存しました。")

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
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
            lock_fp.close()
            print("✓ プロセスロックを解放しました")

if __name__ == "__main__":
    generate_vectors()
