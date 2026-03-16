from .base import BaseScraper, ScrapedPlan

# MNOs
from .ee import EEScraper
from .three import ThreeScraper
from .vodafone import VodafoneScraper
from .o2 import O2Scraper

# MVNOs
from .giffgaff import GiffgaffScraper
from .voxi import VoxiScraper
from .tesco_mobile import TescoMobileScraper
from .asda_mobile import AsdaMobileScraper
from .id_mobile import IDMobileScraper
from .lyca_mobile import LycaMobileScraper
from .talkmobile import TalkmobileScraper

# Affiliates
from .uswitch import USwitchScraper
from .moneysupermarket import MoneySupermarketScraper
from .moneysavingexpert import MoneySavingExpertScraper
from .mobile_phones_direct import MobilePhonesDirectScraper
from .carphone_warehouse import CarphoneWarehouseScraper

SCRAPERS = [
    # MNOs
    EEScraper,
    ThreeScraper,
    VodafoneScraper,
    O2Scraper,
    # MVNOs
    GiffgaffScraper,
    VoxiScraper,
    TescoMobileScraper,
    AsdaMobileScraper,
    IDMobileScraper,
    LycaMobileScraper,
    TalkmobileScraper,
    # Affiliates
    USwitchScraper,
    MoneySupermarketScraper,
    MoneySavingExpertScraper,
    MobilePhonesDirectScraper,
    CarphoneWarehouseScraper,
]
