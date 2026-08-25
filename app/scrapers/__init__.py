from .remoteok import RemoteOKScraper
from .arbeitnow import ArbeitnowScraper
from .jobicy import JobicyScraper

AVAILABLE_SCRAPERS = {
    "remoteok": RemoteOKScraper,
    "arbeitnow": ArbeitnowScraper,
    "jobicy": JobicyScraper,
}