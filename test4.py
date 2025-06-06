import requests
from bs4 import BeautifulSoup

# 1. スクレイピング対象のURL
url = 'https://tabelog.com/tokyo/A1302/A130201/13213760/dtlrvwlst/COND-0/smp1/?smp=1&photo_count_per_review=1'

# 2. requestsを使ってURLのHTMLコンテンツを取得
try:
    response = requests.get(url)
    # HTTPエラーがあれば例外を発生させる
    response.raise_for_status()

    # 3. BeautifulSoupでHTMLを解析
    soup = BeautifulSoup(response.content, 'html.parser')

    # 4. 口コミが書かれているdivタグをすべて見つける
    # ご提示の画像から，口コミは 'rvw-item__rvw-comment' というクラス名を持つdivに含まれていることが分かります．
    review_elements = soup.find_all('div', class_='rvw-item__rvw-comment')

    # 5. 見つけた各要素からテキストを抽出して表示
    print(f"--- 取得した口コミ一覧 ({len(review_elements)}件) ---")
    for i, review in enumerate(review_elements):
        # .get_text(strip=True) で，タグを取り除いたテキストのみを取得し，余分な空白を削除します．
        review_text = review.get_text(strip=True)
        print(f"【口コミ {i+1}】")
        print(review_text)
        print("-" * 20)

except requests.exceptions.RequestException as e:
    print(f"エラーが発生しました: {e}")