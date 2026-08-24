from .remoteok import RemoteOKScraper
from .arbeitnow import ArbeitnowScraper

AVAILABLE_SCRAPERS = {
    "remoteok": RemoteOKScraper,
    "arbeitnow": ArbeitnowScraper,
}