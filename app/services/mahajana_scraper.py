import re
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from app.services.scraper import Scraper

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30  # seconds

NLB_BASE_URL = "https://www.nlb.lk"


class NLBScraper(Scraper):
    """Object-oriented scraper for NLB lottery pages.

    Use `scrape_draw(draw_id)` to fetch and parse a single draw.
    """

    def __init__(self, lottery_name: str):
        self.lottery_name = lottery_name
        self.session: requests.Session | None = None

    @staticmethod
    def _extract_cookie_from_script(html_content: str) -> tuple[str | None, str | None]:
        pattern = r"setCookie\(['\"]([^'\"]+)['\"],['\"]([^'\"]+)['\"],\d+\)"
        match = re.search(pattern, html_content)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def _get_nlb_session(self) -> requests.Session:
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        try:
            response = session.get(f"{NLB_BASE_URL}/lotteries", timeout=REQUEST_TIMEOUT)
            cookie_name, cookie_value = self._extract_cookie_from_script(response.text)
            if cookie_name and cookie_value:
                session.cookies.set(cookie_name, cookie_value, domain="www.nlb.lk", path="/")
        except Exception:
            logger.warning("Failed to set up NLB session", exc_info=True)

        self.session = session
        return session

    @staticmethod
    def _parse_draw_number(draw_block) -> str | None:
        h1_tag = draw_block.find("h1")
        if h1_tag:
            match = re.search(r"\b(\d{3,5})\b", h1_tag.get_text(strip=True))
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _parse_date(draw_block) -> str | None:
        for p in draw_block.find_all("p"):
            b_tag = p.find("b")
            if b_tag and "Date:" in b_tag.get_text():
                return p.get_text(strip=True).replace("Date:", "").replace('"', "").strip()
        return None

    @staticmethod
    def _parse_numbers_and_letter(draw_block) -> tuple[list[str], str | None]:
        numbers: list[str] = []
        letter: str | None = None
        for li in draw_block.select("ol.B li"):
            li_classes = li.get("class", [])
            text = li.get_text(strip=True)
            if "Letter" in li_classes:
                letter = text
            elif text.isdigit():
                numbers.append(text)
        return numbers, letter

    def scrape_draw(self, draw_id: int) -> dict:
        url = f"{NLB_BASE_URL}/results/{self.lottery_name}/{draw_id}"
        session = self._get_nlb_session() if not self.session else self.session

        try:
            response = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=REQUEST_TIMEOUT)
            soup = BeautifulSoup(response.text, "html.parser")

            draw_block = soup.find("div", class_="lresult")
            if not draw_block:
                logger.info("No results found for draw %s — likely not released yet", draw_id)
                return None

            numbers, letter = self._parse_numbers_and_letter(draw_block)

            return {
                "lottery_name": self.lottery_name,
                "draw_no": self._parse_draw_number(draw_block),
                "date": self._parse_date(draw_block),
                "letter": letter,
                "numbers": numbers,
            }
        finally:
            try:
                session.close()
            except Exception:
                pass

    # Conform to Scraper ABC: provide a generic `scrape` method
    def scrape(self, draw_id: int) -> dict:
        return self.scrape_draw(draw_id)


def scrape_draw(draw_id: int, lottery_name: str) -> dict:
    """Compatibility wrapper that uses the OOP scraper under the hood."""
    scraper = NLBScraper(lottery_name)
    return scraper.scrape_draw(draw_id)
