from abc import ABC, abstractmethod
from typing import Any

# Abstract base class:
class Scraper(ABC):
    """Abstract base class for scrapers.

    Subclasses must implement `scrape(...)` which returns parsed results.
    """

    @abstractmethod
    def scrape(self, *args: Any, **kwargs: Any):
        raise NotImplementedError()


class ScraperFactory:
    """Standard factory class for creating scraper instances."""

    @staticmethod
    def create_scraper(provider: str, lottery_name: str | None = None):
        """Return the correct scraper instance for the provider."""
        prov = (provider or "").strip().lower()
        if prov in ("nlb", "mahajana"):
            from .mahajana_scraper import NLBScraper

            return NLBScraper(lottery_name)

        if prov in ("dlb", "dlb.lk"):
            from .dlb_scraper import DLBScraper

            return DLBScraper()

        raise ValueError(f"Unknown scraper provider: {provider}")


def get_scraper(provider: str, lottery_name: str | None = None):
    """Compatibility wrapper around the ScraperFactory."""
    return ScraperFactory.create_scraper(provider, lottery_name)
