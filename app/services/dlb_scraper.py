import re
import logging
import time
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
import urllib3
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from app.services.scraper import Scraper

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 25  # seconds
DLB_BASE_URL = "https://www.dlb.lk"
DLB_PAGINATION_URL = f"{DLB_BASE_URL}/result/pagination_re"

# Headers required by the DLB web server to prevent HTTP 406 Not Acceptable
DLB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{DLB_BASE_URL}/result/en",
    "Origin": DLB_BASE_URL,
}

# The 9 active DLB lotteries
ACTIVE_DLB_LOTTERIES = {
    11: {"id": 11, "name": "Ada Kotipathi", "slug": "ada-kotipathi"},
    1:  {"id": 1,  "name": "Shanida", "slug": "shanida"},
    2:  {"id": 2,  "name": "Lagna Wasana", "slug": "lagna-wasana"},
    17: {"id": 17, "name": "Supiri Dhana Sampatha", "slug": "supiri-dhana-sampatha"},
    3:  {"id": 3,  "name": "Super Ball", "slug": "super-ball"},
    12: {"id": 12, "name": "Kapruka", "slug": "kapruka"},
    19: {"id": 19, "name": "Waasi", "slug": "waasi"},
    13: {"id": 13, "name": "Sasiri", "slug": "sasiri"},
    18: {"id": 18, "name": "Jaya Sampatha", "slug": "jaya-sampatha"},
}

# Explicitly rejected archived lotteries
ARCHIVED_DLB_LOTTERIES = {
    6:  "Jayoda",
    9:  "Development Fortune",
    15: "Vasantha Perk",
    16: "Instant",
}

# Lookup by slug for convenience
_SLUG_TO_ID = {info["slug"]: lot_id for lot_id, info in ACTIVE_DLB_LOTTERIES.items()}
_NAME_TO_ID = {info["name"].lower(): lot_id for lot_id, info in ACTIVE_DLB_LOTTERIES.items()}

ZODIAC_MAP = {
    "mesha": "Mesha (Aries)",
    "vrishabha": "Vrishabha (Taurus)",
    "mithuna": "Mithuna (Gemini)",
    "kataka": "Kataka (Cancer)",
    "simha": "Simha (Leo)",
    "kanya": "Kanya (Virgo)",
    "thula": "Thula (Libra)",
    "vrushchika": "Vrishchika (Scorpio)",
    "dhanu": "Dhanu (Sagittarius)",
    "makara": "Makara (Capricorn)",
    "kumbha": "Kumbha (Aquarius)",
    "meena": "Meena (Pisces)",
}


class ArchivedLotteryError(ValueError):
    """Raised when an archived DLB lottery is requested."""
    pass


class UnknownLotteryError(ValueError):
    """Raised when an unrecognised DLB lottery ID or slug is requested."""
    pass


def validate_active_lottery(lottery_id_or_identifier: int | str) -> dict:
    """Validate that the lottery is one of the 9 active DLB lotteries.

    Raises:
        ArchivedLotteryError: If the lottery is in ARCHIVED_DLB_LOTTERIES.
        UnknownLotteryError: If the lottery is not recognized as active.
    """
    lot_id = None
    if isinstance(lottery_id_or_identifier, int):
        lot_id = lottery_id_or_identifier
    elif isinstance(lottery_id_or_identifier, str):
        if lottery_id_or_identifier.isdigit():
            lot_id = int(lottery_id_or_identifier)
        else:
            slug = lottery_id_or_identifier.strip().lower()
            lot_id = _SLUG_TO_ID.get(slug) or _NAME_TO_ID.get(slug)

    # Check if archived
    if lot_id in ARCHIVED_DLB_LOTTERIES:
        archived_name = ARCHIVED_DLB_LOTTERIES[lot_id]
        logger.warning("Rejected archived DLB lottery: %s (ID: %s)", archived_name, lot_id)
        raise ArchivedLotteryError(
            f"Lottery '{archived_name}' (ID: {lot_id}) is archived and rejected from the pipeline."
        )

    # Check if active
    if lot_id not in ACTIVE_DLB_LOTTERIES:
        logger.warning("Rejected unsupported DLB lottery identifier: %s", lottery_id_or_identifier)
        raise UnknownLotteryError(
            f"DLB lottery '{lottery_id_or_identifier}' is unknown or not an active DLB lottery. "
            f"Active IDs: {list(ACTIVE_DLB_LOTTERIES.keys())}"
        )

    return ACTIVE_DLB_LOTTERIES[lot_id]


def resolve_lottery_id(val: int | str) -> int:
    """Resolve lottery ID or slug/name to integer ID, verifying active status."""
    return validate_active_lottery(val)["id"]


def get_active_lotteries() -> list[dict]:
    """Return a list of all active DLB lotteries."""
    return list(ACTIVE_DLB_LOTTERIES.values())


def _get_dlb_session() -> requests.Session:
    """Return a requests.Session configured with connection pool and retry adapter."""
    session = requests.Session()
    retries = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


get_requests_session = _get_dlb_session


def _parse_dlb_html(html_text: str, lottery_info: dict) -> list[dict]:
    """Parse table rows returned by the DLB pagination endpoint into draw dictionaries."""
    soup = BeautifulSoup(html_text, "html.parser")
    # Finding <td> containing '|' is robust against backend unclosed <tr> tags
    draw_tds = [td for td in soup.find_all("td") if "|" in td.get_text()]
    results = []

    lottery_id = lottery_info["id"]
    lottery_name = lottery_info["name"]

    for first_td in draw_tds:
        text0 = first_td.get_text(strip=True)
        parts = text0.split("|")
        draw_no = parts[0].strip()
        date_day_part = parts[1].strip() if len(parts) > 1 else ""

        # Parse date and day (e.g. "2026-Nov-15 Sunday")
        m_date = re.match(r"(\d{4}-[A-Za-z]+-\d{1,2})\s*([A-Za-z]*)", date_day_part)
        if m_date:
            raw_date = m_date.group(1)
            try:
                draw_date = datetime.strptime(raw_date, "%Y-%b-%d").strftime("%Y-%m-%d")
            except Exception:
                draw_date = raw_date
        else:
            draw_date = date_day_part

        parent_tr = first_td.parent
        all_tds = parent_tr.find_all("td", recursive=False)

        # Col 1: Special Symbol / Zodiac Sign (Lagna Wasana)
        special_symbol = ""
        if len(all_tds) > 1:
            img = all_tds[1].find("img")
            if img and img.get("src"):
                src = img["src"]
                filename = src.split("/")[-1]
                m_sign = re.search(r"[a-zA-Z]+", filename.split(".")[0])
                if m_sign:
                    sign_key = m_sign.group(0).lower()
                    special_symbol = ZODIAC_MAP.get(sign_key, m_sign.group(0).capitalize())

        # Col 2: Numbers, Letter, Special Number
        special_letter = ""
        winning_numbers = []
        special_number = None

        if len(all_tds) > 2:
            res_td = all_tds[2]

            # English letter
            let_li = res_td.find("li", class_=re.compile(r"res_eng_letter|eng_letter"))
            if let_li and let_li.get_text(strip=True):
                special_letter = let_li.get_text(strip=True)

            # Numbers
            num_lis = res_td.find_all("li", class_=re.compile(r"res_number|number_shanida|number_circle"))
            for nli in num_lis:
                style = nli.get("style", "")
                val = nli.get_text(strip=True)
                if not val or not val.isdigit():
                    continue
                num_int = int(val)
                # Background color indicates bonus / special number (e.g. Kapruka bonus ball)
                if "background-color" in style or "bonus" in nli.get("class", []):
                    special_number = num_int
                else:
                    winning_numbers.append(num_int)

            # Fallback if no specific li classes
            if not winning_numbers and not special_letter:
                tokens = res_td.get_text(separator=" ", strip=True).split()
                for tok in tokens:
                    if tok.isalpha() and len(tok) == 1:
                        special_letter = tok
                    elif tok.isdigit():
                        winning_numbers.append(int(tok))

        # Col 3 & 4: Extra numbers if any
        for c in [3, 4]:
            if len(all_tds) > c:
                extra = [
                    int(li.get_text(strip=True))
                    for li in all_tds[c].find_all("li")
                    if li.get_text(strip=True).isdigit()
                ]
                if extra:
                    winning_numbers.extend(extra)

        # Col 5: Special Draw Data (modal image or 2nd chance indicator)
        special_draw = ""
        if len(all_tds) > 5:
            sp_td = all_tds[5]
            modal = sp_td.find("div", class_=re.compile(r"modal"))
            if modal:
                modal_img = modal.find("img")
                if modal_img and modal_img.get("src"):
                    special_draw = modal_img["src"]
            if not special_draw:
                sp_img = sp_td.find("img")
                if sp_img and sp_img.get("src") and "symbol_special" not in sp_img["src"]:
                    special_draw = sp_img["src"]
            if not special_draw:
                txt = sp_td.get_text(strip=True)
                if txt and txt != "×":
                    special_draw = txt

        results.append({
            "lottery_id": lottery_id,
            "lottery_name": lottery_name,
            "draw_no": draw_no,
            "date": draw_date,
            "letter": special_letter,
            "numbers": winning_numbers,
            "special_symbol": special_symbol,
            "special_number": special_number,
            "special_draw": special_draw,
        })

    return results


def scrape_dlb_page(lottery_id_or_slug: int | str, page_id: int = 0) -> list[dict]:
    """Scrape a single pagination page of an active DLB lottery.

    Rejects archived lotteries.

    Args:
        lottery_id_or_slug: Numeric ID (e.g. 11) or slug (e.g. 'ada-kotipathi').
        page_id: Pagination page index (0 is latest 12 draws).

    Returns:
        List of parsed draw records.
    """
    lottery_info = validate_active_lottery(lottery_id_or_slug)
    lottery_id = lottery_info["id"]

    session = _get_dlb_session()
    data = {
        "pageId": page_id,
        "resultID": 0,
        "lotteryID": lottery_id,
        "lastsegment": "en",
    }

    try:
        response = session.post(
            DLB_PAGINATION_URL,
            data=data,
            headers=DLB_HEADERS,
            verify=False,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            if "No Data Found" in response.text:
                return []
            return _parse_dlb_html(response.text, lottery_info)
        elif response.status_code == 406:
            logger.error("DLB endpoint returned 406 Not Acceptable (check request headers)")
            return []
        else:
            logger.warning("DLB pagination returned status %s for lot %s page %s", response.status_code, lottery_id, page_id)
            return []
    except Exception:
        logger.exception("Failed to scrape DLB page %s for lottery %s", page_id, lottery_id)
        return []
    finally:
        session.close()


def scrape_dlb_latest(lottery_id_or_slug: int | str) -> dict | None:
    """Scrape the latest draw record for a specific active DLB lottery.

    Rejects archived lotteries.
    """
    lottery_info = validate_active_lottery(lottery_id_or_slug)
    draws = scrape_dlb_page(lottery_info["id"], page_id=0)
    if draws:
        return draws[0]
    return None


def scrape_all_active_dlb_latest() -> list[dict]:
    """Scrape the latest draw record for all 9 active DLB lotteries."""
    latest_draws = []
    for lot_id, info in ACTIVE_DLB_LOTTERIES.items():
        try:
            draw = scrape_dlb_latest(lot_id)
            if draw:
                latest_draws.append(draw)
            else:
                logger.warning("[%s] No latest draw returned", info["name"])
        except Exception:
            logger.exception("[%s] Error scraping latest draw", info["name"])
    return latest_draws


def scrape_dlb_historical(lottery_id_or_slug: int | str, max_pages: int | None = None, delay: float = 0.2) -> list[dict]:
    """Scrape all available historical draws for an active DLB lottery.

    Paginates until 'No Data Found' or `max_pages` is reached.
    Rejects archived lotteries.
    """
    lottery_info = validate_active_lottery(lottery_id_or_slug)
    lot_id = lottery_info["id"]
    all_draws = []
    page = 0
    empty_streak = 0

    while True:
        if max_pages is not None and page >= max_pages:
            break

        draws = scrape_dlb_page(lot_id, page_id=page)
        if not draws:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0
            all_draws.extend(draws)

        page += 1
        time.sleep(delay)

    return all_draws


class DLBScraper(Scraper):
    """
    Production-grade object-oriented scraper for DLB lotteries.
    Implements Scraper abstract base class.
    """

    def scrape(self, lottery_id: int | str, lottery_name: str | None = None, limit: int = 20, **kwargs) -> list[dict]:
        target_val = lottery_id or lottery_name
        lottery_info = validate_active_lottery(target_val)
        lid = lottery_info["id"]

        results: list[dict] = []
        page = 0

        while len(results) < limit:
            page_draws = scrape_dlb_page(lid, page_id=page)
            if not page_draws:
                break
            results.extend(page_draws)
            page += 1
            time.sleep(0.2)

        return results[:limit]


def scrape_dlb(lottery_id: int | str, lottery_name: str = "", limit: int = 20) -> list[dict]:
    """Backwards-compatible wrapper function."""
    return DLBScraper().scrape(lottery_id, lottery_name, limit=limit)


def run_all() -> None:
    """Run scrape for all 9 active DLB lotteries and persist to database."""
    from app.services.db import insert_dlb_draw

    print("\n=== Running DLB Daily Scraper for all 9 active lotteries ===")
    total_new = 0

    for lid, info in ACTIVE_DLB_LOTTERIES.items():
        print(f"\n[+] Scraping {info['name']} (ID {lid})...")
        try:
            draw = scrape_dlb_latest(lid)
            if draw:
                if insert_dlb_draw(draw):
                    total_new += 1
                    print(f"  ✓ Inserted draw #{draw['draw_no']} ({draw['date']})")
                else:
                    print(f"  - Draw #{draw['draw_no']} already in DB")
            else:
                print(f"  ! No draw returned for {info['name']}")
        except Exception as e:
            print(f"  ❌ Error for {info['name']}: {e}")
        time.sleep(0.3)

    print(f"\n=== Finished: {total_new} new draws inserted ===")


if __name__ == "__main__":
    run_all()
