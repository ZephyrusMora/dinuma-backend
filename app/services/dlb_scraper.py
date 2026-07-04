from playwright.sync_api import sync_playwright
from app.services.db import insert_dlb_draw
from app.services.scraper import Scraper
import re

BASE_URL = "https://www.dlb.lk"

LOTTERY_MAPPING = {
    ""
    "": 13,
    "shanida": 1,
    "jayoda": 6,
    "kapruka": 12,
    "super-ball": 3,
    "ada-kotipathi": 11,
    "supiri-dhana-sampatha": 17
}

# Concrete scraper classes
class DLBScraper(Scraper):
    """Object-oriented wrapper around the DLB scraping logic."""

    BASE_URL = BASE_URL

    @staticmethod
    def clean(text: str) -> str:
        text = text.replace("MORE", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def parse_block(block: str):
        block = DLBScraper.clean(block)

        header_match = re.search(r"(\d{3,5})\s*\|\s*([A-Za-z0-9\s\-,:]+)", block)
        if not header_match:
            return None

        draw_no = header_match.group(1).strip()
        after_header = header_match.group(2).strip()

        after_header = re.sub(
            r"(DRAW NUMBER|AND DATE|RESULTS|Special Draw/2nd Chance)",
            "",
            after_header,
            flags=re.IGNORECASE,
        ).strip()

        letter = ""
        numbers = []

        compact = re.search(r"([A-Z])?(\d{6,10})", after_header)
        if compact:
            letter = compact.group(1) or ""
            raw = compact.group(2)
            numbers = [int(raw[i:i+2]) for i in range(0, len(raw), 2)]
        else:
            nums = re.findall(r"\b\d{2}\b", after_header)
            numbers = [int(n) for n in nums[:3]]

        date = re.sub(r"[A-Z]\d+|\d{6,}", "", after_header)
        date = DLBScraper.clean(date)

        return draw_no, date, letter, numbers

    def scrape(self, lottery_id: int, lottery_name: str, limit=20):
        results = []
        seen = set()

        url = f"{self.BASE_URL}/result/{lottery_id}/"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            print(f"\n[+] Opening {lottery_name} ({lottery_id})")

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            body_text = page.inner_text("body")

            blocks = re.split(r"(?=\d{3,5}\s*\|)", body_text)

            for block in blocks:

                if len(results) >= limit:
                    break

                parsed = DLBScraper.parse_block(block)
                if not parsed:
                    continue

                draw_no, date, letter, numbers = parsed

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
                    "numbers": numbers,
                }

                results.append(item)

                try:
                    insert_dlb_draw(item)
                except Exception as e:
                    print("DB error:", e)

        return results


def scrape_dlb(lottery_id: int, lottery_name: str, limit=20):
    """Compatibility wrapper that uses the `DLBScraper` class."""
    return DLBScraper().scrape(lottery_id, lottery_name, limit=limit)


def run_all():
    for name, lid in LOTTERY_MAPPING.items():
        print("\n==============================")
        print(name, lid)
        print("==============================")

        try:
            data = scrape_dlb(lid, name, limit=20)

            for d in data:
                print(d)

        except Exception as e:
            print(f"❌ Failed {name}: {e}")


if __name__ == "__main__":
    run_all()