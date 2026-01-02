import os
import time
import random
import csv
import json
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime


class TabelogScraper:
    def __init__(self, headless=False):
        """
        初期化
        :param headless: ヘッドレスモードで実行するか
        """
        options = webdriver.ChromeOptions()
        
        # 基本設定
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        # プロファイル破損による起動失敗を防ぐための一時ディレクトリ使用
        user_data_dir = tempfile.mkdtemp()
        options.add_argument(f'--user-data-dir={user_data_dir}')
        
        # ヘッドレスモードの設定
        if headless:
            options.add_argument("--headless=new")
        
        # 検出回避・安定化
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        print("ChromeDriverを起動しています...")
        try:
            # webdriver-manager を使用して ChromeDriver を自動管理
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 10)
            print("ChromeDriver起動成功")
        except Exception as e:
            print(f"ChromeDriver起動エラー: {e}")
            raise e

    def extract_store_info(self, url):
        """
        店舗情報を抽出
        :param url: 店舗ページのURL
        :return: 店舗情報の辞書
        """
        print(f"アクセス中: {url}")
        self.driver.get(url)
        time.sleep(3)  # ページ読み込み待機（安全のため3秒）

        store_data = {
            'store_id': '',
            'store_name': '',
            'genre': '',
            'rating': '',
            'url': url,
            'reviews': []
        }

        try:
            # 店舗ID（URLから抽出）
            store_data['store_id'] = url.rstrip('/').split('/')[-1]

            # 店舗名
            try:
                store_name = self.driver.find_element(By.CSS_SELECTOR, '.display-name').text
                store_data['store_name'] = store_name
            except NoSuchElementException:
                print("店舗名が見つかりません")

            # ジャンル
            try:
                genre_elem = self.driver.find_element(By.CSS_SELECTOR, '.rdheader-subinfo__item--cuisine')
                store_data['genre'] = genre_elem.text
            except NoSuchElementException:
                try:
                    # 別のセレクタを試す
                    genre_elem = self.driver.find_element(By.XPATH, "//th[contains(text(), 'ジャンル')]/following-sibling::td")
                    store_data['genre'] = genre_elem.text
                except:
                    print("ジャンルが見つかりません")

            # 総合スコア（星評価）
            try:
                rating_elem = self.driver.find_element(By.CSS_SELECTOR, '.rdheader-rating__score-val-dtl')
                store_data['rating'] = rating_elem.text
            except NoSuchElementException:
                try:
                    # 別のセレクタを試す
                    rating_elem = self.driver.find_element(By.CLASS_NAME, 'c-rating__val')
                    store_data['rating'] = rating_elem.text
                except:
                    print("評価スコアが見つかりません")

            print(f"店舗情報取得完了: {store_data['store_name']} (評価: {store_data['rating']})")

        except Exception as e:
            print(f"店舗情報の取得エラー: {e}")

        return store_data

    def extract_reviews(self, store_url, max_pages=None, max_reviews=None):
        """
        レビューを抽出（全ページ）
        :param store_url: 店舗URL
        :param max_pages: 取得する最大ページ数（Noneの場合は全ページ）
        :param max_reviews: 取得する最大レビュー件数（Noneの場合は制限なし）
        :return: レビューのリスト
        """
        reviews = []

        # レビューページに移動
        review_url = store_url.rstrip('/') + '/dtlrvwlst/'
        self.driver.get(review_url)
        time.sleep(3)  # ページ読み込み待機（安全のため3秒）

        page_count = 0

        while True:
            page_count += 1
            print(f"レビューページ {page_count} を取得中...")

            try:
                # 全ての「もっと見る」ボタンをクリック
                click_count = 0
                while True:
                    try:
                        # 正しいセレクタで「もっと見る」ボタンを探す
                        button = self.driver.find_element(By.XPATH, "//span[@class='rvw-showall-trigger__target']")

                        if button and button.is_displayed():
                            # 親要素（クリック可能な要素）を取得
                            parent = button.find_element(By.XPATH, "..")
                            # スクロールしてボタンを表示
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", parent)
                            time.sleep(0.01)  # スクロール待機（極限まで短縮）
                            # クリック
                            self.driver.execute_script("arguments[0].click();", parent)
                            click_count += 1
                            time.sleep(0.5)  # クリック待機
                        else:
                            break
                    except NoSuchElementException:
                        # もう「もっと見る」ボタンがない
                        break
                    except Exception as e:
                        # その他のエラーで停止
                        break

                if click_count > 0:
                    print(f"  {click_count} 個の「もっと見る」ボタンをクリックしました")

                # レビューアイテムを取得
                review_items = self.driver.find_elements(By.CSS_SELECTOR, '.rvw-item')
                processed_this_page = 0

                for item in review_items:
                    review = {}

                    try:
                        # レビュアー名
                        reviewer = item.find_element(By.CSS_SELECTOR, '.rvw-item__rvwr-name a').text
                        review['reviewer'] = reviewer
                    except:
                        review['reviewer'] = ''

                    try:
                        # レビュー評価
                        rating = item.find_element(By.CSS_SELECTOR, '.rvw-item__ratings .c-rating__val').text
                        review['review_rating'] = rating
                    except:
                        review['review_rating'] = ''

                    try:
                        # レビュー日付
                        date = item.find_element(By.CSS_SELECTOR, '.rvw-item__date').text
                        review['review_date'] = date
                    except:
                        review['review_date'] = ''

                    try:
                        # レビュー本文を取得
                        text_elem = item.find_element(By.CSS_SELECTOR, '.rvw-item__rvw-comment p')
                        review['review_text'] = text_elem.text
                    except:
                        review['review_text'] = ''

                    reviews.append(review)
                    processed_this_page += 1

                    if max_reviews and len(reviews) >= max_reviews:
                        break

                print(f"  {processed_this_page} 件のレビューを取得")

                # 最大ページ数チェック
                if max_pages and page_count >= max_pages:
                    print(f"最大ページ数 {max_pages} に到達しました")
                    break

                if max_reviews and len(reviews) >= max_reviews:
                    print(f"最大レビュー数 {max_reviews} 件に到達しました")
                    break

                # 次のページボタンを探す
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, '.c-pagination__arrow--next')

                    # リンクが無効かチェック
                    if 'c-pagination__arrow--disabled' in next_button.get_attribute('class'):
                        print("最終ページに到達しました")
                        break

                    # 次のページに移動
                    next_button.click()
                    time.sleep(2)  # ページ読み込み待機（安全のため2秒）

                except NoSuchElementException:
                    print("次のページボタンが見つかりません（最終ページ）")
                    break

            except Exception as e:
                print(f"レビュー取得エラー: {e}")
                break

        print(f"合計 {len(reviews)} 件のレビューを取得しました")
        return reviews

    def scrape_store(self, url, max_review_pages=None, max_review_count=None):
        """
        1つの店舗の全データを取得
        :param url: 店舗URL
        :param max_review_pages: レビューの最大ページ数
        :param max_review_count: レビュー件数の上限
        :return: 店舗データ
        """
        # 店舗情報を取得
        store_data = self.extract_store_info(url)

        # レビューを取得
        reviews = self.extract_reviews(url, max_pages=max_review_pages, max_reviews=max_review_count)
        store_data['reviews'] = reviews

        return store_data

    def save_to_json(self, data, filename='tabelog_data.json'):
        """
        JSONファイルに保存
        """
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"データを {filename} に保存しました")

    def save_to_csv(self, data, filename='tabelog_data.csv'):
        """
        CSVファイルに保存（フラット化）
        """
        rows = []
        for store in data:
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
                # レビューがない場合
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
            print(f"データを {filename} に保存しました")

    def close(self):
        """
        ブラウザを閉じる
        """
        self.driver.quit()

class Tokyo23KuTabelogScraper(TabelogScraper):
    # エリア名からコードへの変換辞書
    AREA_MAP = {
        '千代田区': 'C13101', '中央区': 'C13102', '港区': 'C13103', '新宿区': 'C13104',
        '文京区': 'C13105', '台東区': 'C13106', '墨田区': 'C13107', '江東区': 'C13108',
        '品川区': 'C13109', '目黒区': 'C13110', '大田区': 'C13111', '世田谷区': 'C13112',
        '渋谷区': 'C13113', '中野区': 'C13114', '杉並区': 'C13115', '豊島区': 'C13116',
        '北区': 'C13117', '荒川区': 'C13118', '板橋区': 'C13119', '練馬区': 'C13120',
        '足立区': 'C13121', '葛飾区': 'C13122', '江戸川区': 'C13123',
    }

    @staticmethod
    def load_url_list(url_list_path):
        """外部URLリスト(JSON)を読み込んで area_code -> URL配列 に整形"""
        with open(url_list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        normalized = {}
        if isinstance(data, dict):
            for code, value in data.items():
                if isinstance(value, dict) and isinstance(value.get('urls'), list):
                    normalized[code] = value['urls']
                elif isinstance(value, list):
                    normalized[code] = value
        elif isinstance(data, list):
            for entry in data:
                code = entry.get('area_code')
                url = entry.get('url')
                if code and url:
                    normalized.setdefault(code, []).append(url)

        return normalized

    def get_urls_by_area(self, area_code, target_count):
        """特定のエリアコードから指定した店舗数分のURLを回収"""
        area_urls = []
        page = 1
        while len(area_urls) < target_count:
            url = f"https://tabelog.com/tokyo/{area_code}/rstLst/{page}/"
            self.driver.get(url)
            time.sleep(random.uniform(3, 6)) # 負荷軽減のため長めに設定（ランダム化）
            
            links = self.driver.find_elements(By.CSS_SELECTOR, 'a.list-rst__rst-name-target')
            if not links:
                links = self.driver.find_elements(By.CSS_SELECTOR, 'a.list-rst__name')
            if not links: break
            
            for link in links:
                href = link.get_attribute('href').split('?')[0].rstrip('/')
                if '/tokyo/A' in href and href.count('/') >= 6 and '/lst/' not in href:
                    if href not in area_urls:
                        area_urls.append(href)
                if len(area_urls) >= target_count: break
            
            print(f"    ページ {page}: {len(area_urls)}/{target_count} 件のURL確保")
            try:
                next_btn = self.driver.find_element(By.CSS_SELECTOR, '.c-pagination__arrow--next')
                if 'c-pagination__arrow--disabled' in next_btn.get_attribute('class'): break
                page += 1
            except: break
        return area_urls

    def execute_23ku_workflow(
        self,
        stores_per_area,
        output_json,
        output_csv,
        max_review_pages=None,
        max_review_count=40,
        is_debug=False,
        target_names=None,
        per_area_start=0,
        per_area_limit=None,
        url_list_path=None,
    ):
        """
        ワークフロー実行
        :param target_names: エリア名のリスト（例：['新宿', '渋谷']）
        :param max_review_count: 1店舗あたりの最大レビュー件数
        :param per_area_start: 各エリアのURLリストでスキップする件数
        :param per_area_limit: 各エリアで処理する最大件数（Noneで制限なし）
        :param url_list_path: 事前に生成したURLリストJSONのパス
        """
        all_data = []
        processed_store_ids = set()
        preloaded_urls = None

        if os.path.exists(output_json):
            try:
                with open(output_json, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    if isinstance(existing_data, list):
                        all_data = existing_data
                        processed_store_ids = {store.get('store_id') for store in existing_data if store.get('store_id')}
                        print(f"既存データ {len(all_data)} 件を読み込みました（{len(processed_store_ids)} 店舗）。")
            except Exception as e:
                print(f"既存データの読み込みに失敗しました: {e}")
        
        # 名前からコードに変換。指定がなければ全区。
        if target_names:
            area_codes = [self.AREA_MAP[name] for name in target_names if name in self.AREA_MAP]
        else:
            area_codes = [f"C131{i:02d}" for i in range(1, 24)]
        
        mode_name = "【デバッグモード】" if is_debug else "【本番スクレイピング】"
        print(f"\n{'='*70}\n{mode_name}\n対象エリア: {target_names if target_names else '全23区'}\n{'='*70}")

        if url_list_path:
            try:
                preloaded_urls = self.load_url_list(url_list_path)
                print(f"事前URLリストを読み込みました: {len(preloaded_urls)} エリア")
            except Exception as e:
                print(f"URLリストの読み込みに失敗しました: {e}")
                preloaded_urls = None

        for code in area_codes:
            print(f"\nエリアコード {code} を処理中...")
            if preloaded_urls is not None:
                target_urls = preloaded_urls.get(code, [])
                if not target_urls:
                    print("  URLリストに対象が無いためスキップ")
                    continue
            else:
                target_urls = self.get_urls_by_area(code, stores_per_area)
            start_idx = min(per_area_start, len(target_urls))
            end_idx = len(target_urls) if per_area_limit is None else min(start_idx + per_area_limit, len(target_urls))
            selected_urls = target_urls[start_idx:end_idx]
            print(f"  URL取得: {len(target_urls)} 件 → 使用範囲 {start_idx}〜{end_idx} (計 {len(selected_urls)} 件)")
            
            for idx, url in enumerate(selected_urls, 1):
                try:
                    store_id = url.rstrip('/').split('/')[-1]
                    if store_id in processed_store_ids:
                        print(f"  [{code}] 既存データのためスキップ: {store_id}")
                        continue

                    print(f"  [{code}] 進捗: {idx}/{len(selected_urls)}店舗目")
                    store_data = self.scrape_store(url, max_review_pages=max_review_pages, max_review_count=max_review_count)
                    all_data.append(store_data)
                    if store_data.get('store_id'):
                        processed_store_ids.add(store_data['store_id'])
                    
                    if len(all_data) % 5 == 0:
                        self.save_to_json(all_data, output_json)
                        self.save_to_csv(all_data, output_csv)
                    time.sleep(2)
                except Exception as e:
                    print(f"  [!] エラースキップ: {e}")
                    continue
        
        self.save_to_json(all_data, output_json)
        self.save_to_csv(all_data, output_csv)
        print(f"\n{'='*70}\n完了！合計 {len(all_data)} 店舗\n{'='*70}")

# --- 実行用関数（エリア指定対応） ---

def run_specific_areas_debug(
    area_list,
    stores_per_area=20,
    max_review_count=40,
    per_area_start=0,
    per_area_limit=None,
    url_list_path=None,
):
    scraper = Tokyo23KuTabelogScraper(headless=True)
    try:
        scraper.execute_23ku_workflow(
            stores_per_area=stores_per_area,
            output_json='tabelog_debug_selected2.json',
            output_csv='tabelog_debug_selected2.csv',
            max_review_pages=None,
            max_review_count=max_review_count,
            is_debug=True,
            target_names=area_list,
            per_area_start=per_area_start,
            per_area_limit=per_area_limit,
            url_list_path=url_list_path,
        )
    finally:
        scraper.close()

# --- メイン実行 ---
if __name__ == '__main__':
    # ご希望のエリアリスト
    target_areas = [
        '江東区'
    ]
    
    # デバッグ実行（例: 事前URLリストを使用し各区1200店舗のうち前半600件・レビュー最大40件）
    run_specific_areas_debug(
        target_areas,
        stores_per_area=1200,
        max_review_count=100,
        per_area_start=276,
        per_area_limit=124, 
        url_list_path='/Users/dangararara/lecture/miraisouzou/20251220/tabelog_url_list.json',
    )


