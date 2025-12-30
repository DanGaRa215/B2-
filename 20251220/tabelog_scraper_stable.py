"""
安定性を向上させたスクレイピングコード
ChromeDriverのクラッシュ対策版
"""

import time
import csv
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class StableTabelogScraper:
    def __init__(self, headless=False):
        """
        安定性を重視した初期化
        """
        options = Options()

        # 安定性を高めるオプション
        if headless:
            options.add_argument('--headless=new')  # 新しいヘッドレスモード

        # 基本設定
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')

        # クラッシュ対策
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-blink-features=AutomationControlled')

        # メモリ関連
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--shm-size=2gb')

        # User Agent
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')

        # ログレベルを下げる
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        try:
            # Service の設定
            service = Service(ChromeDriverManager().install())

            # ドライバーの初期化
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)  # タイムアウト設定
            self.wait = WebDriverWait(self.driver, 10)

            print("✓ ChromeDriver初期化成功")

        except Exception as e:
            print(f"✗ ChromeDriver初期化エラー: {e}")
            raise

    def safe_get(self, url, retry=3):
        """
        安全なページ取得（リトライ機能付き）
        """
        for attempt in range(retry):
            try:
                self.driver.get(url)
                time.sleep(2)
                return True
            except Exception as e:
                print(f"  リトライ {attempt + 1}/{retry}: {e}")
                if attempt == retry - 1:
                    raise
                time.sleep(3)
        return False

    def extract_store_info(self, url):
        """店舗情報を抽出"""
        print(f"アクセス中: {url}")

        try:
            self.safe_get(url)
        except Exception as e:
            print(f"ページ取得エラー: {e}")
            return None

        store_data = {
            'store_id': '',
            'store_name': '',
            'genre': '',
            'rating': '',
            'url': url,
            'reviews': []
        }

        try:
            store_data['store_id'] = url.rstrip('/').split('/')[-1]

            try:
                store_name = self.driver.find_element(By.CSS_SELECTOR, '.display-name').text
                store_data['store_name'] = store_name
            except NoSuchElementException:
                print("  店舗名が見つかりません")

            try:
                genre_elem = self.driver.find_element(By.CSS_SELECTOR, '.rdheader-subinfo__item--cuisine')
                store_data['genre'] = genre_elem.text
            except NoSuchElementException:
                try:
                    genre_elem = self.driver.find_element(By.XPATH, "//th[contains(text(), 'ジャンル')]/following-sibling::td")
                    store_data['genre'] = genre_elem.text
                except:
                    print("  ジャンルが見つかりません")

            try:
                rating_elem = self.driver.find_element(By.CSS_SELECTOR, '.rdheader-rating__score-val-dtl')
                store_data['rating'] = rating_elem.text
            except NoSuchElementException:
                try:
                    rating_elem = self.driver.find_element(By.CLASS_NAME, 'c-rating__val')
                    store_data['rating'] = rating_elem.text
                except:
                    print("  評価スコアが見つかりません")

            print(f"  店舗情報取得: {store_data['store_name']} (評価: {store_data['rating']})")

        except Exception as e:
            print(f"  店舗情報取得エラー: {e}")

        return store_data

    def extract_reviews(self, store_url, max_pages=None):
        """レビューを抽出"""
        reviews = []
        review_url = store_url.rstrip('/') + '/dtlrvwlst/'

        try:
            self.safe_get(review_url)
        except Exception as e:
            print(f"  レビューページ取得エラー: {e}")
            return reviews

        page_count = 0

        while True:
            page_count += 1
            print(f"  レビューページ {page_count}")

            try:
                # 「もっと見る」ボタンをクリック
                click_count = 0
                max_clicks = 50  # 無限ループ防止

                while click_count < max_clicks:
                    try:
                        button = self.driver.find_element(By.XPATH, "//span[@class='rvw-showall-trigger__target']")
                        if button and button.is_displayed():
                            parent = button.find_element(By.XPATH, "..")
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", parent)
                            time.sleep(0.1)
                            self.driver.execute_script("arguments[0].click();", parent)
                            click_count += 1
                            time.sleep(0.2)
                        else:
                            break
                    except NoSuchElementException:
                        break
                    except Exception:
                        break

                # レビューアイテムを取得
                review_items = self.driver.find_elements(By.CSS_SELECTOR, '.rvw-item')

                for item in review_items:
                    review = {}

                    try:
                        reviewer = item.find_element(By.CSS_SELECTOR, '.rvw-item__rvwr-name a').text
                        review['reviewer'] = reviewer
                    except:
                        review['reviewer'] = ''

                    try:
                        rating = item.find_element(By.CSS_SELECTOR, '.rvw-item__ratings .c-rating__val').text
                        review['review_rating'] = rating
                    except:
                        review['review_rating'] = ''

                    try:
                        date = item.find_element(By.CSS_SELECTOR, '.rvw-item__date').text
                        review['review_date'] = date
                    except:
                        review['review_date'] = ''

                    try:
                        text_elem = item.find_element(By.CSS_SELECTOR, '.rvw-item__rvw-comment p')
                        review['review_text'] = text_elem.text
                    except:
                        review['review_text'] = ''

                    reviews.append(review)

                print(f"    {len(review_items)} 件のレビューを取得")

                if max_pages and page_count >= max_pages:
                    break

                # 次のページへ
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, '.c-pagination__arrow--next')
                    if 'c-pagination__arrow--disabled' in next_button.get_attribute('class'):
                        break
                    next_button.click()
                    time.sleep(2)
                except NoSuchElementException:
                    break

            except Exception as e:
                print(f"  レビュー取得エラー: {e}")
                break

        print(f"  合計 {len(reviews)} 件のレビュー")
        return reviews

    def scrape_store(self, url, max_review_pages=None):
        """1つの店舗をスクレイピング"""
        store_data = self.extract_store_info(url)

        if store_data is None:
            return None

        reviews = self.extract_reviews(url, max_review_pages)
        store_data['reviews'] = reviews
        return store_data

    def save_to_json(self, data, filename):
        """JSONに保存"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  → {filename} に保存")

    def save_to_csv(self, data, filename):
        """CSVに保存"""
        rows = []
        for store in data:
            if store is None:
                continue

            if store['reviews']:
                for review in store['reviews']:
                    row = {
                        '店舗ID': store['store_id'],
                        '店舗名': store['store_name'],
                        'ジャンル': store['genre'],
                        '総合評価': store['rating'],
                        '店舗URL': store['url'],
                        'レビュアー': review.get('reviewer', ''),
                        'レビュー評価': review.get('review_rating', ''),
                        'レビュー日付': review.get('review_date', ''),
                        'レビュー本文': review.get('review_text', '')
                    }
                    rows.append(row)
            else:
                row = {
                    '店舗ID': store['store_id'],
                    '店舗名': store['store_name'],
                    'ジャンル': store['genre'],
                    '総合評価': store['rating'],
                    '店舗URL': store['url'],
                    'レビュアー': '',
                    'レビュー評価': '',
                    'レビュー日付': '',
                    'レビュー本文': ''
                }
                rows.append(row)

        if rows:
            with open(filename, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            print(f"  → {filename} に保存")

    def close(self):
        """ブラウザを閉じる"""
        try:
            self.driver.quit()
            print("✓ ブラウザを終了")
        except:
            pass


# テスト実行
if __name__ == '__main__':
    print("="*70)
    print("安定版スクレイパーのテスト")
    print("="*70)

    scraper = StableTabelogScraper(headless=False)

    try:
        # テスト用URL
        test_url = 'https://tabelog.com/tokyo/A1303/A130301/13000001/'

        store_data = scraper.scrape_store(test_url, max_review_pages=2)

        if store_data:
            scraper.save_to_json([store_data], 'test_stable.json')
            scraper.save_to_csv([store_data], 'test_stable.csv')
            print("\n✓ テスト成功")
        else:
            print("\n✗ テスト失敗")

    except Exception as e:
        print(f"\n✗ エラー: {e}")
    finally:
        scraper.close()
