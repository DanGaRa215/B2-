"""
江戸川区、墨田区、文京区、大田区の店舗リストを元に口コミをスクレイピング
"""
from scrayping_tabelog import Tokyo23KuTabelogScraper

def main():
    # 対象エリア
    target_areas = [
        '江戸川区',
        '墨田区',
        '文京区',
        '大田区'
    ]

    # URLリストのパス
    url_list_path = 'tabelog_edogawa_sumida_bunkyou_oota.json'

    # 出力ファイル名
    output_json = 'tabelog_edogawa_sumida_bunkyou_oota_reviews.json'
    output_csv = 'tabelog_edogawa_sumida_bunkyou_oota_reviews.csv'

    # スクレイパーの初期化
    scraper = Tokyo23KuTabelogScraper(headless=True)

    try:
        scraper.execute_23ku_workflow(
            stores_per_area=1200,  # URLリストから取得するので、この値は使われない
            output_json=output_json,
            output_csv=output_csv,
            max_review_pages=None,  # 全ページ取得
            max_review_count=100,  # 1店舗あたり最大100件のレビュー
            is_debug=False,  # 本番モード
            target_names=target_areas,
            per_area_start=0,  # 最初から
            per_area_limit=None,  # 全店舗
            url_list_path=url_list_path,  # 事前に生成したURLリスト
        )
    finally:
        scraper.close()

    print(f"\n完了！")
    print(f"JSON: {output_json}")
    print(f"CSV: {output_csv}")

if __name__ == '__main__':
    main()
