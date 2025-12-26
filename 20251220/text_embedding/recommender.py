import psycopg2
import torch
import numpy as np
import pandas as pd
from transformers import BertJapaneseTokenizer, BertModel
from sklearn.metrics.pairwise import cosine_similarity

class StoreRecommender:
    def __init__(self, db_name='tabelog_db', user='dangararara'):
        self.db_name = db_name
        self.user = user
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        if torch.backends.mps.is_available():
            self.device = 'mps'
        
        print(f"Loading model on {self.device}...")
        self.model_name = 'cl-tohoku/bert-base-japanese-v3'
        self.tokenizer = BertJapaneseTokenizer.from_pretrained(self.model_name)
        self.model = BertModel.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()
        
        self.store_vectors = None
        self.store_data = None
        self._load_store_data()

    def _load_store_data(self):
        """DBから店舗ベクトルと基本情報をロード"""
        try:
            conn = psycopg2.connect(host="localhost", database=self.db_name, user=self.user)
            
            # ベクトルと評価点を取得
            query = """
            SELECT
                s.store_id,
                s.store_name,
                s.overall_rating,
                s.store_url,
                v.feature_vector
            FROM stores s
            JOIN store_vectors v ON s.store_id = v.store_id
            WHERE s.overall_rating IS NOT NULL
            """
            df = pd.read_sql(query, conn)

            self.store_ids = df['store_id'].tolist()
            self.store_names = df['store_name'].tolist()
            self.store_urls = df['store_url'].tolist()
            self.ratings = df['overall_rating'].values
            
            # ベクトルをnumpy配列に変換
            vectors = df['feature_vector'].tolist()
            self.store_vectors = np.array(vectors)
            
            # 評価点を0-1に正規化 (Min-Max scaling)
            min_rating = 3.0 # 食べログの仕様上、実質的な下限
            max_rating = 5.0
            self.normalized_ratings = (self.ratings - min_rating) / (max_rating - min_rating)
            self.normalized_ratings = np.clip(self.normalized_ratings, 0, 1)
            
            print(f"Loaded {len(df)} stores.")
            
        except Exception as e:
            print(f"Error loading data: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    def _encode_query(self, query_text):
        """クエリテキストをベクトル化"""
        inputs = self.tokenizer(
            query_text, 
            return_tensors='pt', 
            max_length=512, 
            truncation=True, 
            padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            last_hidden_state = outputs.last_hidden_state
            attention_mask = inputs['attention_mask'].unsqueeze(-1).expand(last_hidden_state.size()).float()
            sum_embeddings = torch.sum(last_hidden_state * attention_mask, 1)
            sum_mask = torch.clamp(attention_mask.sum(1), min=1e-9)
            mean_embeddings = sum_embeddings / sum_mask
            return mean_embeddings.cpu().numpy()

    def search(self, query_text, alpha=0.5, top_k=5):
        """
        検索を実行
        Score = alpha * Similarity + (1 - alpha) * NormalizedRating
        """
        # クエリベクトル生成
        query_vector = self._encode_query(query_text)
        
        # コサイン類似度計算
        similarities = cosine_similarity(query_vector, self.store_vectors)[0]
        
        # スコア計算
        # 類似度は-1~1なので、0~1に正規化しておくと扱いやすいが、
        # ここでは単純にコサイン類似度(通常0以上が多い)をそのまま使うか、
        # 必要に応じて (sim + 1) / 2 などで正規化する。
        # 今回はBERTの出力同士なので正の相関が強いと仮定し、そのまま使用。
        
        final_scores = alpha * similarities + (1 - alpha) * self.normalized_ratings
        
        # 上位を取得
        top_indices = np.argsort(final_scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append({
                'store_name': self.store_names[idx],
                'store_url': self.store_urls[idx],
                'score': final_scores[idx],
                'similarity': similarities[idx],
                'rating': self.ratings[idx],
                'norm_rating': self.normalized_ratings[idx]
            })

        return results
