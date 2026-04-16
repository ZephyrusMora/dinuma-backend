"""
Standalone script for Heroku Scheduler to run the daily scrape.

Usage:
    python run_scrape.py

Heroku Scheduler calls this as a one-off process, so it's not
affected by dyno restarts or cold boots.
"""
from app.services.dlb_scraper import run_all

if __name__ == "__main__":
    run_all()