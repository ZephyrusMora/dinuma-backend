from abc import ABC, abstractmethod
from typing import Any


class Scraper(ABC):
    """Abstract base class for scraper implementations."""

    @abstractmethod
    def scrape(self, *args: Any, **kwargs: Any):
        raise NotImplementedError()


class ScraperFactory:
    """Factory for creating and running scraper instances."""

    @staticmethod
    def create_scraper(provider: str, lottery_name: str | None = None):
        """Return the correct scraper instance for the given provider."""
        prov = (provider or "").strip().lower()
        if prov in ("nlb", "mahajana"):
            from .mahajana_scraper import NLBScraper

            return NLBScraper(lottery_name)

        if prov in ("dlb", "dlb.lk"):
            from .dlb_scraper import DLBScraper

            return DLBScraper()

        raise ValueError(f"Unknown scraper provider: {provider}")

    @staticmethod
    def scrape(provider: str, *args: Any, lottery_name: str | None = None, **kwargs: Any):
        """Create a scraper and execute it through the shared interface."""
        scraper = ScraperFactory.create_scraper(provider, lottery_name=lottery_name)
        return scraper.scrape(*args, **kwargs)


def get_scraper(provider: str, lottery_name: str | None = None):
    """Compatibility wrapper around the scraper factory."""
    return ScraperFactory.create_scraper(provider, lottery_name)
