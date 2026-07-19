-- 食べログデータベース テーブル作成
-- PostgreSQL用

-- 既存テーブルを削除（初回は不要）
DROP TABLE IF EXISTS reviews CASCADE;
DROP TABLE IF EXISTS stores CASCADE;

-- 店舗テーブル
CREATE TABLE stores (
    store_id VARCHAR(50) PRIMARY KEY,
    store_name VARCHAR(255) NOT NULL,
    genre VARCHAR(100),
    overall_rating NUMERIC(3, 2),
    store_url VARCHAR(500) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- レビューテーブル
CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    store_id VARCHAR(50) NOT NULL,
    review_rating NUMERIC(3, 2),
    review_date DATE,
    review_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);

-- インデックス作成
CREATE INDEX idx_store_name ON stores(store_name);
CREATE INDEX idx_store_genre ON stores(genre);
CREATE INDEX idx_store_rating ON stores(overall_rating DESC);
CREATE INDEX idx_reviews_store_id ON reviews(store_id);
CREATE INDEX idx_reviews_date ON reviews(review_date DESC);
CREATE INDEX idx_reviews_rating ON reviews(review_rating DESC);

-- 確認用クエリ
SELECT 'Tables created successfully!' as status;
\dt
