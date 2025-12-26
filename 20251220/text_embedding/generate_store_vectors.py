import psycopg2
import torch
from transformers import BertJapaneseTokenizer, BertModel
import pandas as pd
import numpy as np
from tqdm import tqdm

# モデル設定
MODEL_NAME = 'cl-tohoku/bert-base-japanese-v3'
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
if torch.backends.mps.is_available():
    DEVICE = 'mps' # Mac M1/M2用

print(f"Using device: {DEVICE}")

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
    # 1. モデルとトークナイザーのロード
    print("モデルをロード中...")
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
        print(f"取得完了: {len(df)} 店舗")

        # 4. ベクトル生成と保存
        print("ベクトル生成を開始します...")
        
        batch_size = 16
        total_processed = 0
        
        for i in tqdm(range(0, len(df), batch_size)):
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

        print(f"完了: {total_processed} 店舗のベクトルを保存しました。")

    except Exception as e:
        print(f"エラー: {e}")
        conn.rollback()
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    generate_vectors()
