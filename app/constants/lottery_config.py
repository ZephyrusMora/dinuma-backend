"""
Configuration for all Sri Lankan Lotteries (NLB & DLB).
Defines game rules, ball pool sizes, draw counts, and bonus feature flags.
"""
from typing import Dict, Any

LOTTERIES: Dict[str, Dict[str, Any]] = {
    # ── NLB Category (from jaya_draws table) ──
    "govisetha": {
        "id": "govisetha",
        "name": "Govisetha",
        "category": "NLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 numbers (1-80) + bonus English letter"
    },
    "mahajana-sampatha": {
        "id": "mahajana-sampatha",
        "name": "Mahajana Sampatha",
        "category": "NLB",
        "type": "digit",
        "pool": 10,  # 0-9
        "count_per_draw": 6,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "6 digits (0-9) + bonus English letter"
    },
    "dhana-nidhanaya": {
        "id": "dhana-nidhanaya",
        "name": "Dhana Nidhanaya",
        "category": "NLB",
        "type": "number",
        "pool": 90,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 numbers (1-90) + bonus English letter"
    },
    "mega-power": {
        "id": "mega-power",
        "name": "Mega Power",
        "category": "NLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": True,
        "special_pool": 30,
        "description": "Power ball (1-30) + 4 numbers (1-80) + bonus English letter"
    },
    "nlb-jaya": {
        "id": "nlb-jaya",
        "name": "NLB Jaya",
        "category": "NLB",
        "type": "digit",
        "pool": 10,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 digits (0-9) + bonus English letter"
    },

    # ── DLB Category (from dlb_draws table) ──
    "ada-kotipathi": {
        "id": "ada-kotipathi",
        "dlb_id": 11,
        "name": "Ada Kotipathi",
        "category": "DLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 numbers (1-80) + bonus English letter"
    },
    "shanida": {
        "id": "shanida",
        "dlb_id": 1,
        "name": "Shanida",
        "category": "DLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 numbers (1-80) + bonus English letter"
    },
    "lagna-wasana": {
        "id": "lagna-wasana",
        "dlb_id": 2,
        "name": "Lagna Wasana",
        "category": "DLB",
        "type": "number",
        "pool": 70,
        "count_per_draw": 4,
        "has_letter": False,
        "has_symbol": True,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 numbers (1-70) + astrological Zodiac sign"
    },
    "super-ball": {
        "id": "super-ball",
        "dlb_id": 3,
        "name": "Super Ball",
        "category": "DLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 numbers (1-80) + bonus English letter"
    },
    "kapruka": {
        "id": "kapruka",
        "dlb_id": 12,
        "name": "Kapruka",
        "category": "DLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": True,
        "special_pool": 40,
        "description": "Special number (1-40) + 4 numbers (1-80) + bonus English letter"
    },
    "sasiri": {
        "id": "sasiri",
        "dlb_id": 13,
        "name": "Sasiri",
        "category": "DLB",
        "type": "number",
        "pool": 50,
        "count_per_draw": 3,
        "has_letter": False,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "3 numbers (1-50)"
    },
    "supiri-dhana-sampatha": {
        "id": "supiri-dhana-sampatha",
        "dlb_id": 17,
        "name": "Supiri Dhana Sampatha",
        "category": "DLB",
        "type": "digit",
        "pool": 10,
        "count_per_draw": 6,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "6 digits (0-9) + bonus English letter"
    },
    "jaya-sampatha": {
        "id": "jaya-sampatha",
        "dlb_id": 18,
        "name": "Jaya Sampatha",
        "category": "DLB",
        "type": "digit",
        "pool": 10,
        "count_per_draw": 4,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": False,
        "special_pool": None,
        "description": "4 digits (0-9) + bonus English letter"
    },
    "waasi": {
        "id": "waasi",
        "dlb_id": 19,
        "name": "Waasi",
        "category": "DLB",
        "type": "number",
        "pool": 80,
        "count_per_draw": 2,
        "has_letter": True,
        "has_symbol": False,
        "has_special_num": True,
        "special_pool": 20,
        "description": "Special number + 2 numbers + bonus English letter"
    },
}

# Mapping of DLB integer ID to slug
DLB_ID_TO_SLUG = {
    cfg["dlb_id"]: slug
    for slug, cfg in LOTTERIES.items()
    if "dlb_id" in cfg
}
