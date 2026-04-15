from .unified_base import UnifiedScraper, ScrapedPlan

BaseScraper = UnifiedScraper

from .ee import EEScraper
from .three import ThreeScraper
from .vodafone import VodafoneScraper
from .o2 import O2Scraper
from .giffgaff import giffgaffScraper
from .voxi import VOXIScraper
from .tesco_mobile import TescoMobileScraper
from .asda_mobile import AsdaMobileScraper
from .id_mobile import iDMobileScraper
from .lyca_mobile import LycaMobileScraper
from .talkmobile import TalkmobileScraper
from .sky_mobile import SkyMobileScraper
from .uswitch import USwitchScraper
from .moneysupermarket import MoneySupermarketScraper
from .moneysavingexpert import MoneySavingExpertScraper
from .mobilephonesdirect import MobilePhonesDirectScraper
from .carphonewarehouse import CarphoneWarehouseScraper
from .mobilescouk import MobilesCoUkScraper
from .mozillion import MozillionScraper

SCRAPERS = [
    EEScraper,
    ThreeScraper,
    VodafoneScraper,
    O2Scraper,
    giffgaffScraper,
    VOXIScraper,
    TescoMobileScraper,
    AsdaMobileScraper,
    iDMobileScraper,
    LycaMobileScraper,
    TalkmobileScraper,
    SkyMobileScraper,
    USwitchScraper,
    MoneySupermarketScraper,
    MoneySavingExpertScraper,
    MobilePhonesDirectScraper,
    CarphoneWarehouseScraper,
    MobilesCoUkScraper,
    MozillionScraper,
]
