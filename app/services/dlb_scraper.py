from playwright.sync_api import sync_playwright
from app.services.db import insert_dlb_draw
import re

BASE_URL = "https://www.dlb.lk"

LOTTERY_MAPPING = {
    "sasiri": 13,
    "shanida": 1,
    "jayoda": 6,
    "kapruka": 12,
    "super-ball": 3,
    "ada-kotipathi": 11,
    "supiri-dhana-sampatha": 17
}


# CLEAN
def clean(text: str):
    text = text.replace("MORE", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# PARSER 
def parse_block(block: str):
    block = clean(block)

    # DRAW + DATE (STRICT)
    header_match = re.search(r"(\d{3,5})\s*\|\s*([A-Za-z0-9\s\-,:]+)", block)
    if not header_match:
        return None

    draw_no = header_match.group(1).strip()
    after_header = header_match.group(2).strip()

    # REMOVE GARBAGE TEXT
    after_header = re.sub(
        r"(DRAW NUMBER|AND DATE|RESULTS|Special Draw/2nd Chance)",
        "",
        after_header,
        flags=re.IGNORECASE
    ).strip()

    # LETTER + RESULT EXTRACTION
    letter = ""
    numbers = []

    # CASE 1: F14194767 OR Z29576067
    compact = re.search(r"([A-Z])?(\d{6,10})", after_header)
    if compact:
        letter = compact.group(1) or ""
        raw = compact.group(2)
        numbers = [int(raw[i:i+2]) for i in range(0, len(raw), 2)]

    else:
        # CASE 2: spaced numbers (21 32 40)
        nums = re.findall(r"\b\d{2}\b", after_header)
        numbers = [int(n) for n in nums[:3]]

    # CLEAN DATE (ONLY TEXT)
    date = re.sub(r"[A-Z]\d+|\d{6,}", "", after_header)
    date = clean(date)

    return draw_no, date, letter, numbers


# SCRAPER
def scrape_dlb(lottery_id: int, lottery_name: str, limit=10):
    results = []
    seen = set()

    url = f"{BASE_URL}/result/{lottery_id}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"\n[+] Opening {lottery_name} ({lottery_id})")

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        body_text = page.inner_text("body")

        # split safely per draw
        blocks = re.split(r"(?=\d{3,5}\s*\|)", body_text)

        for block in blocks:

            if len(results) >= limit:
                break

            parsed = parse_block(block)
            if not parsed:
                continue

            draw_no, date, letter, numbers = parsed

            # HARD VALIDATION
            if not draw_no or not numbers:
                continue

            key = f"{lottery_id}-{draw_no}"
            if key in seen:
                continue
            seen.add(key)

            item = {
                "lottery_name": lottery_name,
                "lottery_id": lottery_id,
                "draw_no": draw_no,
                "date": date,
                "letter": letter,
                "numbers": numbers
            }

            results.append(item)

            try:
                insert_dlb_draw(item)
            except Exception as e:
                print("DB error:", e)

    return results

# RUN ALL
def run_all():
    for name, lid in LOTTERY_MAPPING.items():
        print("\n==============================")
        print(name, lid)
        print("==============================")

        try:
            data = scrape_dlb(lid, name, limit=5)

            for d in data:
                print(d)

        except Exception as e:
            print(f"❌ Failed {name}: {e}")


if __name__ == "__main__":
    run_all()