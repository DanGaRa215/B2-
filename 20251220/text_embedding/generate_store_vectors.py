import psycopg2
import torch
from transformers import BertJapaneseTokenizer, BertModel
import pandas as pd
import numpy as np
import fcntl
import sys
import os

# モデル設定
MODEL_NAME = 'cl-tohoku/bert-base-japanese-v3'

# MPSは不安定なためCPUモードで実行（安定性優先）
DEVICE = 'cpu'
print(f"Using device: {DEVICE} (CPUモード - 安定性優先)")

def get_store_reviews(conn):
    """
    店舗ごとのレビューを結合して取得
    """
    query = """
    SELECT 
        s.store_id,
        string_agg(r.review_text, ' ') as combined_text
    FROM stores s
    JOIN reviews r ON s.store_id = r.store_id
    GROUP BY s.store_id
    """
    return pd.read_sql(query, conn)

def generate_vectors(db_name='tabelog_db', user='dangararara'):
    # プロセスロックの取得（同時実行を防ぐ）
    lock_file = '/tmp/generate_store_vectors.lock'
    lock_fp = open(lock_file, 'w')
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("✓ プロセスロックを取得しました")
    except IOError:
        print("❌ エラー: 既に別のプロセスが実行中です")
        print("他のプロセスが完了するまで待つか、停止してから再実行してください")
        sys.exit(1)

    # 1. モデルとトークナイザーのロード
    print("モデルをロード中...")

    # マルチプロセス処理を無効化（resource_tracker警告対策）
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'

    tokenizer = BertJapaneseTokenizer.from_pretrained(MODEL_NAME)
    model = BertModel.from_pretrained(MODEL_NAME)
    model.to(DEVICE)
    model.eval()
    print("モデルロード完了")

    # 2. DB接続
    try:
        conn = psycopg2.connect(host="localhost", database=db_name, user=user)
        cur = conn.cursor()
        
        # 3. データ取得
        print("レビューデータを取得中...")
        df = get_store_reviews(conn)
        print(f"全店舗数: {len(df)} 店舗")

        # 既存のベクトル済み店舗を取得してスキップ
        try:
            cur.execute("SELECT store_id FROM store_vectors")
            existing_ids = set(row[0] for row in cur.fetchall())
            print(f"ベクトル生成済み: {len(existing_ids)} 店舗")
            
            df = df[~df['store_id'].isin(existing_ids)]
            print(f"今回処理対象: {len(df)} 店舗")
        except Exception as e:
            print(f"既存データの確認中にエラー（初回実行時は無視してください）: {e}")
            conn.rollback()

        if len(df) == 0:
            print("全ての店舗のベクトル生成が完了しています。")
            return

        # 4. ベクトル生成と保存
        print("ベクトル生成を開始します...")

        # バッチサイズを小さくしてメモリ使用量を削減（MPS対策）
        batch_size = 4  # 16 -> 4 に変更
        total_processed = 0

        # 進捗表示
        total_batches = (len(df) + batch_size - 1) // batch_size
        print(f"総バッチ数: {total_batches}")

        for batch_idx, i in enumerate(range(0, len(df), batch_size)):
            batch = df.iloc[i:i+batch_size]
            texts = batch['combined_text'].tolist()
            store_ids = batch['store_id'].tolist()
            
            # トークナイズ (最大長512で切り詰め)
            inputs = tokenizer(
                texts, 
                return_tensors='pt', 
                max_length=512, 
                truncation=True, 
                padding=True
            )
            
            inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
                # 最終層の隠れ状態の平均を使用 (Mean Pooling)
                # attention_maskを考慮して平均を取る
                last_hidden_state = outputs.last_hidden_state
                attention_mask = inputs['attention_mask'].unsqueeze(-1).expand(last_hidden_state.size()).float()
                sum_embeddings = torch.sum(last_hidden_state * attention_mask, 1)
                sum_mask = torch.clamp(attention_mask.sum(1), min=1e-9)
                mean_embeddings = sum_embeddings / sum_mask
                
                # CPUに戻してNumPy配列化
                vectors = mean_embeddings.cpu().numpy()
            
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
            total_processed += len(batch)

            # 10バッチごとに進捗を表示
            if (batch_idx + 1) % 10 == 0:
                cur.execute("SELECT COUNT(*) FROM store_vectors")
                current_total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM stores")
                all_stores = cur.fetchone()[0]
                progress_pct = current_total / all_stores * 100
                print(f"  バッチ {batch_idx + 1}/{total_batches} | 完了: {current_total}/{all_stores} ({progress_pct:.1f}%)")

            # Mac (MPS) の場合のメモリ解放処理
            if DEVICE == 'mps':
                torch.mps.empty_cache()

        print(f"\n✓ 完了: {total_processed} 店舗のベクトルを保存しました。")

    except Exception as e:
        print(f"❌ エラー: {e}")
        conn.rollback()
    finally:
        if 'conn' in locals() and conn:
            conn.close()
        # ロックファイルを解放
        if 'lock_fp' in locals():
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
            lock_fp.close()
            print("✓ プロセスロックを解放しました")

if __name__ == "__main__":
    import traceback
    try:
        generate_vectors()
    except Exception as e:
        print(f"\n致命的エラー: {e}")
        traceback.print_exc()
        sys.exit(1)
