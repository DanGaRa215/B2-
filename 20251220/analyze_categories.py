"""
カテゴリ（ジャンル）の分析
"""
import psycopg2
import pandas as pd
from collections import Counter

def analyze_categories(db_name='tabelog_db', user='dangararara'):
    conn = psycopg2.connect(host="localhost", database=db_name, user=user)

    # 全店舗のジャンルを取得
    query = "SELECT store_id, genre FROM stores WHERE genre IS NOT NULL"
    df = pd.read_sql(query, conn)

    print(f"総店舗数: {len(df)}")
    print(f"ジャンル組み合わせ数: {df['genre'].nunique()}")

    # カンマ区切りで分解して個別カテゴリを抽出
    all_categories = []
    for genre_str in df['genre']:
        # "焼肉、ホルモン、居酒屋" → ["焼肉", "ホルモン", "居酒屋"]
        categories = [cat.strip() for cat in genre_str.split('、')]
        all_categories.extend(categories)

    # 個別カテゴリの出現回数をカウント
    category_counts = Counter(all_categories)

    print(f"\n個別カテゴリの種類数: {len(category_counts)}")
    print(f"\nTOP 30 カテゴリ:")
    print("-" * 50)
    for category, count in category_counts.most_common(30):
        print(f"{category:20s} : {count:4d} 店舗")

    # 店舗ごとのカテゴリ数の分布
    category_nums = df['genre'].apply(lambda x: len(x.split('、')))
    print(f"\n店舗あたりのカテゴリ数:")
    print("-" * 50)
    print(category_nums.value_counts().sort_index())

    conn.close()

    return list(category_counts.keys())

if __name__ == '__main__':
    unique_categories = analyze_categories()
    print(f"\n\n全カテゴリリスト（{len(unique_categories)}種類）:")
    print(unique_categories[:50])  # 最初の50個だけ表示
