"""ベクトル生成スクリプト v5 - 長文/メモリ安全 & 重み付き平均 & オーバーラップ版"""

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

print("=== ベクトル生成スクリプト v5 (長文/メモリ安全 & 重み付き平均 & overlap) ===")
print(f"OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS')}")
print(f"モデル: {MODEL_NAME}")

def weighted_average(vectors: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """
    vectors: (n, dim)
    weights: (n,)
    """
    w = weights.astype(np.float64)
    s = w.sum()
    if s <= 0:
        return np.mean(vectors, axis=0)
    return (vectors * w[:, None]).sum(axis=0) / s

def get_long_text_vector(
    model,
    text: str,
    max_seq_length: int = 512,
    overlap_tokens: int = 128,
    encode_batch_size: int = 16,
) -> np.ndarray:
    """
    512トークン制限を超える長文を:
      - input_ids を max_seq_length-2 の窓でスライド（overlap付き）
      - 各チャンクを encode
      - チャンク長(トークン数)で重み付き平均
    して 1 ベクトルにする。

    改善点:
      - batch_size をチャンク数に合わせず上限固定 (OOM対策)
      - overlap で境界の意味欠落を軽減
      - 重み付き平均で短いチャンクの過大影響を抑制
    """

    if text is None:
        return np.zeros(model.get_sentence_embedding_dimension(), dtype=np.float32)

    text = text.strip()
    if not text:
        return np.zeros(model.get_sentence_embedding_dimension(), dtype=np.float32)

    # トークナイザ警告(Token indices sequence length is longer than...)回避のため
    # 一時的にmodel_max_lengthを大きくして、全テキストをトークン化できるようにする
    original_max_len = model.tokenizer.model_max_length
    model.tokenizer.model_max_length = int(1e9)

    try:
        # add_special_tokens=False: チャンク化後に encode で special token は通常通り付く
        inputs = model.tokenizer(text, add_special_tokens=False)
    finally:
        model.tokenizer.model_max_length = original_max_len

    input_ids = inputs.get('input_ids', [])
    if not input_ids:
        return np.zeros(model.get_sentence_embedding_dimension(), dtype=np.float32)

    # ここは [CLS], [SEP] の分を確保（SentenceTransformer側で付与される想定）
    chunk_size = max_seq_length - 2
    total_tokens = len(input_ids)

    # 短い場合はそのまま
    if total_tokens <= chunk_size:
        return model.encode(text, convert_to_numpy=True)

    # overlap設定（安全に）
    overlap_tokens = int(overlap_tokens)
    overlap_tokens = max(0, min(overlap_tokens, chunk_size - 1))
    step = chunk_size - overlap_tokens  # スライド幅

    chunks = []
    chunk_token_lens = []

    # スライディングウィンドウでチャンク生成
    for start in range(0, total_tokens, step):
        end = min(start + chunk_size, total_tokens)
        chunk_ids = input_ids[start:end]
        if not chunk_ids:
            continue
        chunk_text = model.tokenizer.decode(chunk_ids, skip_special_tokens=True).strip()
        if not chunk_text:
            continue
        chunks.append(chunk_text)
        chunk_token_lens.append(len(chunk_ids))

        if end >= total_tokens:
            break

    if not chunks:
        return np.zeros(model.get_sentence_embedding_dimension(), dtype=np.float32)

    # チャンク数のログ出力（長文の場合のみ）
    if len(chunks) > 5:
        print(f"      [長文処理] {total_tokens}トークン → {len(chunks)}チャンク")

    # OOM回避: batch_size は上限固定（例: 16）
    bs = max(1, int(encode_batch_size))

    chunk_vectors = model.encode(
        chunks,
        batch_size=bs,
        show_progress_bar=False,
        convert_to_numpy=True
    )

    chunk_vectors = np.asarray(chunk_vectors)
    weights = np.asarray(chunk_token_lens)

    # 重み付き平均（トークン数）
    vec = weighted_average(chunk_vectors, weights)
    return vec

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
        except Exception:
            existing_ids = set()
            conn.rollback()

        # 処理対象の店舗データを取得
        print("店舗データを取得中...")
        # ※ 結合順が非決定的になり得るので ORDER BY を追加（列名は環境に合わせて調整）
        query = """
        SELECT
            s.store_id,
            string_agg(r.review_text, ' ' ORDER BY r.review_id) as combined_text
        FROM stores s
        JOIN reviews r ON s.store_id = r.store_id
        GROUP BY s.store_id
        ORDER BY s.store_id
        """
        cur.execute(query)

        # 未処理の店舗のみフィルタ
        all_stores = []
        for store_id, combined_text in cur.fetchall():
            if store_id in existing_ids:
                continue
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

        # get_long_text_vector のパラメータ（必要なら調整）
        LONGTEXT_MAXSEQ = 512
        LONGTEXT_OVERLAP = 128     # 64〜128あたりが無難（大きいほど計算増）
        ENCODE_BS_CAP = 16         # ← ここが「4の問題」対策の本体（上限固定）

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
                    vec = get_long_text_vector(
                        model,
                        text,
                        max_seq_length=LONGTEXT_MAXSEQ,
                        overlap_tokens=LONGTEXT_OVERLAP,
                        encode_batch_size=ENCODE_BS_CAP,
                    )
                    vectors.append(vec)
                vectors = np.array(vectors)
            except Exception as e:
                print(f"  ⚠️  バッチ {batch_idx + 1} でエラー: {e}")
                continue

            # DBに保存（Upsert）
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
            if True:
                cur.execute("SELECT COUNT(*) FROM store_vectors")
                current_total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM stores")
                all_stores_count = cur.fetchone()[0]
                progress_pct = (current_total / all_stores_count * 100) if all_stores_count else 0.0
                print(f"  バッチ {batch_idx + 1}/{total_batches} | 今回: {end_idx}/{total_stores} | 全体: {current_total}/{all_stores_count} ({progress_pct:.1f}%)")
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