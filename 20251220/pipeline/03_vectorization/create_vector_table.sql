-- ベクトル保存用テーブル作成

DROP TABLE IF EXISTS store_vectors;

CREATE TABLE store_vectors (
    store_id VARCHAR(50) PRIMARY KEY,
    feature_vector FLOAT8[], -- ベクトルを配列として保存
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);

SELECT 'Table store_vectors created successfully!' as status;
