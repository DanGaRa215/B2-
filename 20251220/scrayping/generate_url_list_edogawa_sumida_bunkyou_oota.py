import argparse
import json
import time
import random
from datetime import datetime

from scrayping_tabelog import Tokyo23KuTabelogScraper


def parse_area_names(raw):
    area_candidates = list(Tokyo23KuTabelogScraper.AREA_MAP.keys())
    if not raw:
        return area_candidates
    splits = [name.strip() for name in raw.split(',') if name.strip()]
    return splits or area_candidates


def generate_url_list(area_names, stores_per_area, output_path, headless=True):
    scraper = Tokyo23KuTabelogScraper(headless=headless)

    # 既存のJSONファイルがあれば読み込む
    import os
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
            print(f"既存のデータを読み込みました: {output_path}")
        except Exception as e:
            print(f"既存データの読み込みに失敗: {e}")
            results = {
                "_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "stores_per_area": stores_per_area,
                    "areas": area_names,
                }
            }
    else:
        results = {
            "_meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "stores_per_area": stores_per_area,
                "areas": area_names,
            }
        }

    try:
        for name in area_names:
            code = scraper.AREA_MAP.get(name)
            if not code:
                print(f"[!] 未対応エリアのためスキップ: {name}")
                continue

            # 既に取得済みの場合はスキップ
            if code in results and code != "_meta":
                print(f"[!] {name} ({code}) は既に取得済みのためスキップ")
                continue

            print(f"[+] {name} ({code}) のURLを取得中...")
            try:
                urls = scraper.get_urls_by_area(code, stores_per_area)
                results[code] = {
                    "area_name": name,
                    "urls": urls,
                }
                print(f"    -> {len(urls)} 件のURLを取得")

                # 区ごとに即座に保存
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                print(f"    -> {output_path} に保存しました")

                time.sleep(random.uniform(2, 5)) # エリア間の待機時間
            except Exception as e:
                print(f"[!] {name} ({code}) の取得中にエラー: {e}")
                continue
    finally:
        scraper.close()

    print(f"\n完了！URLリストを {output_path} に保存しました")


def main():
    parser = argparse.ArgumentParser(description="Tabelog URLリスト作成ツール")
    parser.add_argument(
        "--areas",
        type=str,
        default='江戸川区,墨田区,文京区,大田区',
        help="対象エリア名をカンマ区切りで指定（例: 新宿区,渋谷区） 未指定なら全23区",
    )
    parser.add_argument(
        "--stores-per-area",
        type=int,
        default=1200,
        help="各エリアで取得する最大店舗数",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="tabelog_edogawa_sumida_bunkyou_oota.json",
        help="保存するJSONファイル名",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Chromeをヘッドレスではなく表示モードで起動",
    )

    args = parser.parse_args()
    area_names = parse_area_names(args.areas)

    generate_url_list(
        area_names=area_names,
        stores_per_area=args.stores_per_area,
        output_path=args.output,
        headless=not args.no_headless,
    )


if __name__ == "__main__":
    main()
