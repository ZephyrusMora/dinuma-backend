from app.services.scraper import ScraperFactory


class DummyScraper:
    def __init__(self, lottery_name=None):
        self.lottery_name = lottery_name

    def scrape(self, *args, **kwargs):
        return {
            "ok": True,
            "args": args,
            "kwargs": kwargs,
            "lottery_name": self.lottery_name,
        }


def test_scraper_factory_scrape_uses_scraper_instance(monkeypatch):
    fake_scraper = DummyScraper(lottery_name="mahajana-sampatha")
    monkeypatch.setattr(
        ScraperFactory,
        "create_scraper",
        lambda provider, lottery_name=None: fake_scraper,
    )

    result = ScraperFactory.scrape("nlb", 123, lottery_name="mahajana-sampatha")

    assert result["ok"] is True
    assert result["args"] == (123,)
    assert result["kwargs"] == {}
    assert result["lottery_name"] == "mahajana-sampatha"
