#!/usr/bin/env python3
"""
読み取りと書き込みでDB接続を分離したバージョン
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import sys
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import normalize


DB_HOST = "localhost"
DB_NAME = "tabelog_db"
DB_USER = "dangararara"
DB_PASSWORD = None

SRC_TABLE = "review_vectors"
RID_COL = "review_id"
VEC_COL = "feature_vector"

OUT_ASSIGN_TABLE = "review_clusters"
OUT_CENTROID_TABLE = "cluster_centroids"

K = 20
USE_L2_NORMALIZE = True
FETCH_CHUNK = 5000
MBK_BATCH_SIZE = 4096
MAX_ITER = 200
N_INIT = 3
RANDOM_STATE = 0
UPSERT_BATCH = 20000


def connect():
    kwargs = dict(host=DB_HOST, database=DB_NAME, user=DB_USER)
    if DB_PASSWORD is not None:
        kwargs["password"] = DB_PASSWORD
    return psycopg2.connect(**kwargs)


def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {OUT_ASSIGN_TABLE} (
            review_id INTEGER PRIMARY KEY,
            cluster_id INTEGER NOT NULL
        );
        """)
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {OUT_CENTROID_TABLE} (
            cluster_id INTEGER PRIMARY KEY,
            centroid_vector FLOAT8[] NOT NULL
        );
        """)
    conn.commit()


def debug_counts(conn):
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {SRC_TABLE};")
        total = cur.fetchone()[0]
        cur.execute(f"""
            SELECT COUNT(*) FROM {SRC_TABLE}
            WHERE {VEC_COL} IS NOT NULL AND array_length({VEC_COL}, 1) IS NOT NULL
        """)
        usable = cur.fetchone()[0]
        cur.execute(f"""
            SELECT array_length({VEC_COL}, 1)
            FROM {SRC_TABLE}
            WHERE {VEC_COL} IS NOT NULL AND array_length({VEC_COL}, 1) IS NOT NULL
            LIMIT 1
        """)
        dim_row = cur.fetchone()
        dim = dim_row[0] if dim_row else None
    print(f"[debug] rows={total:,}, usable_vectors={usable:,}, example_dim={dim}")


def fetch_vectors_in_chunks():
    """
    独立したDB接続でサーバーサイドカーソルを使用
    """
    read_conn = connect()
    try:
        cur = read_conn.cursor(name="read_cursor")
        cur.itersize = FETCH_CHUNK
        cur.execute(f"""
            SELECT {RID_COL}, {VEC_COL}
            FROM {SRC_TABLE}
            WHERE {VEC_COL} IS NOT NULL
              AND array_length({VEC_COL}, 1) IS NOT NULL
            ORDER BY {RID_COL}
        """)

        while True:
            rows = cur.fetchmany(FETCH_CHUNK)
            if not rows:
                break

            ids = []
            vecs = []
            for rid, v in rows:
                if v is None or (hasattr(v, "__len__") and len(v) == 0):
                    continue
                ids.append(int(rid))
                vecs.append(np.asarray(v, dtype=np.float32))

            if not vecs:
                continue

            X = np.vstack(vecs)
            if USE_L2_NORMALIZE:
                X = normalize(X, norm="l2", axis=1, copy=False)

            yield np.asarray(ids, dtype=np.int32), X
    finally:
        read_conn.close()


def fit_kmeans():
    km = MiniBatchKMeans(
        n_clusters=K,
        batch_size=MBK_BATCH_SIZE,
        max_iter=MAX_ITER,
        n_init=N_INIT,
        random_state=RANDOM_STATE,
        verbose=0,
    )

    seen = 0
    for ids, X in fetch_vectors_in_chunks():
        km.partial_fit(X)
        seen += X.shape[0]
        if seen % 200000 == 0:
            print(f"[fit] processed {seen:,} reviews...")

    if seen == 0:
        raise RuntimeError("学習対象ベクトルが0件です。")

    print(f"[fit] done. total reviews used: {seen:,}")
    return km


def upsert_assignments(conn, pairs):
    with conn.cursor() as cur:
        execute_values(
            cur,
            f"""
            INSERT INTO {OUT_ASSIGN_TABLE} (review_id, cluster_id)
            VALUES %s
            ON CONFLICT (review_id) DO UPDATE SET
                cluster_id = EXCLUDED.cluster_id
            """,
            pairs,
            page_size=5000
        )
    conn.commit()


def save_centroids(conn, centroids: np.ndarray):
    pairs = [(int(i), centroids[i].tolist()) for i in range(centroids.shape[0])]
    with conn.cursor() as cur:
        # 前回より K を減らした場合、UPSERT だけでは古い重心が残る。
        # 残った重心は推薦時に選ばれるが対応するレビューが無いため
        # 無言で 0 件を返す原因になるので先に削除する。
        cur.execute(
            f"DELETE FROM {OUT_CENTROID_TABLE} WHERE cluster_id >= %s",
            (centroids.shape[0],)
        )
        if cur.rowcount:
            print(f"[centroids] 古い重心を {cur.rowcount} 個削除しました")
        execute_values(
            cur,
            f"""
            INSERT INTO {OUT_CENTROID_TABLE} (cluster_id, centroid_vector)
            VALUES %s
            ON CONFLICT (cluster_id) DO UPDATE SET
                centroid_vector = EXCLUDED.centroid_vector
            """,
            pairs,
            page_size=500
        )
    conn.commit()


def assign_and_save(write_conn, km: MiniBatchKMeans):
    """書き込み用の接続を受け取る"""
    written = 0
    buf = []

    for ids, X in fetch_vectors_in_chunks():
        pred = km.predict(X).astype(np.int32)

        for rid, cid in zip(ids.tolist(), pred.tolist()):
            buf.append((int(rid), int(cid)))

        if len(buf) >= UPSERT_BATCH:
            upsert_assignments(write_conn, buf)
            written += len(buf)
            buf.clear()
            if written % 200000 == 0:
                print(f"[write] saved {written:,} assignments...")

    if buf:
        upsert_assignments(write_conn, buf)
        written += len(buf)
        buf.clear()

    print(f"[write] done. total saved: {written:,}")


def main():
    write_conn = None
    try:
        print("=== review_vectors clustering ===")
        print(f"DB: {DB_HOST}/{DB_NAME} as {DB_USER}")
        print(f"source: {SRC_TABLE}({RID_COL}, {VEC_COL})")
        print(f"K={K}, L2norm={USE_L2_NORMALIZE}, fetch={FETCH_CHUNK}, mb_batch={MBK_BATCH_SIZE}")

        write_conn = connect()
        ensure_tables(write_conn)
        debug_counts(write_conn)

        km = fit_kmeans()
        assign_and_save(write_conn, km)

        centroids = km.cluster_centers_.astype(np.float32)
        if USE_L2_NORMALIZE:
            centroids = normalize(centroids, norm="l2", axis=1, copy=False)
        save_centroids(write_conn, centroids)

        print("✓ done")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if write_conn:
            write_conn.close()


if __name__ == "__main__":
    main()
