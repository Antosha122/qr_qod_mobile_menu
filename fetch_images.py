"""Fetch canonical 500px thumbnail URLs from Wikimedia Commons via imageinfo API.

Uses specific File: page titles (no hash guessing) and respects rate limits
with small delays. The API is more lenient than the upload.* host for HEAD.
Run: python fetch_images.py
"""
import json
import time
import urllib.parse
import urllib.request

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

# Specific Wikimedia Commons File: titles per menu item.
# (menu_id, [list of candidate file titles]) — first valid wins.
FILES: dict[int, list[str]] = {
    1: [  # Ролл с тунцом
        "File:Fresh and delicious maki roll from Phengphian Laogumnerd Cuisine.jpg",
        "File:Tuna sushi (4968184252).jpg",
    ],
    2: [  # Ролл с креветками
        "File:Chicken Teriyaki Bento + Shrimp Tempura + California Rolls @ Hiro Sushi (5691301632).jpg",
        "File:Ebiten-maki.jpg",
    ],
    3: [  # Ролл с угрем
        "File:DragonRoll.JPG",
        "File:Eel temaki zushi by The Wong Family Pictures.jpg",
    ],
    4: [  # Запеченный ролл с лососем
        "File:Norwegia Roll Salmon Sushi.jpg",
        "File:Homemade sushi rolls, 2009.jpg",
    ],
    5: [  # Запеченный ролл с угрем (унаги)
        "File:Kaidaya Unadon 01.jpg",
        "File:Unagi unadon.jpg",
    ],
    6: [  # Запеченный ролл с курицей
        "File:Chicken Deriyakidon.jpg",
        "File:Chicken Katsu Don with egg - Sakura Sushi Express (1222552412).jpg",
    ],
    7: [  # Классический ролл с огурцом
        "File:Beef maki sushi roll.jpg",
        "File:Kappamaki.jpg",
    ],
    8: [  # Классический ролл с авокадо
        "File:Avocado Maki sushi (Albert Heijn), Hillegersberg, Rotterdam (2023).jpg",
        "File:Papaya Avocado Salmon roll sushi (3688871295).jpg",
    ],
    9: [  # Классический ролл с лососем
        "File:HSY- Sushi, Sake.jpg",
        "File:Salmon sushi.jpg",
    ],
    10: [  # Мисо
        "File:Miso soup essential to Japanese cuisine.jpg",
        "File:Chicken curry, miso soup, Idstein.jpg",
    ],
    11: [  # Рамен
        "File:2023-08-31 Japanese Ramen Soup Noodle.jpg",
        "File:Tonkotsu ramen.jpg",
    ],
    12: [  # Чай
        "File:Cup of Green Tea and Snacks.jpg",
        "File:Green tea steeping.jpg",
    ],
    13: [  # Сок
        "File:Orange juice 1.jpg",
        "File:(a glass of orange juice, a waffle on a nice plate with silverware).jpg",
    ],
}


def get_thumb(file_title: str, width: int = 500) -> str | None:
    """Query imageinfo API for a thumbnail URL of a specific File: page."""
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": width,
        "format": "json",
    })
    url = "https://commons.wikimedia.org/w/api.php?" + params
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except Exception as exc:
        print(f"  ! error for '{file_title}': {exc}")
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        # Missing file -> page has "missing" key
        if "missing" in page:
            continue
        info = (page.get("imageinfo") or [{}])[0]
        thumb = info.get("thumburl")
        mime = info.get("mime", "")
        if thumb and mime in ("image/jpeg", "image/png"):
            return thumb
    return None


def main() -> None:
    results: dict[int, str] = {}
    for item_id, titles in FILES.items():
        found = None
        for title in titles:
            print(f"Item {item_id}: querying '{title}'...")
            found = get_thumb(title)
            if found:
                print(f"  -> {found}")
                break
            time.sleep(0.8)
        if not found:
            print(f"  !! No image for item {item_id}")
        results[item_id] = found or ""
        time.sleep(0.8)

    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    # Print as Python literal for easy copy into models.py
    print("\n=== AS PYTHON DICT ===")
    for item_id, url in results.items():
        print(f"    {item_id}: \"{url}\",")


if __name__ == "__main__":
    main()