"""
date_utils.py — Constantes de períodos de tiempo compartidas entre apps.
Única fuente de verdad para mapas de período → timedelta y período → etiqueta.
"""

from datetime import timedelta


PERIOD_DELTA_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
}

PERIOD_LABEL_MAP: dict[str, str] = {
    "1h": "Última hora",
    "12h": "Últimas 12 horas",
    "24h": "Últimas 24 horas",
    "3d": "Últimos 3 días",
    "7d": "Últimos 7 días",
}
