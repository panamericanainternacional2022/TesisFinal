from django.db import migrations


def seed_umbral_config(apps, schema_editor):
    UmbralConfig = apps.get_model("front", "UmbralConfig")
    defaults = [
        {"variable": "flow_rate",  "direction": "higher", "low": 20,  "medium": 35,  "high": 45},
        {"variable": "pressure",   "direction": "higher", "low": 5,   "medium": 7,   "high": 9},
        {"variable": "temperature","direction": "higher", "low": 70,  "medium": 85,  "high": 100},
        {"variable": "vibration",  "direction": "higher", "low": 4,   "medium": 7,   "high": 10},
        {"variable": "tank_level", "direction": "lower",  "low": 30,  "medium": 15,  "high": 5},
        {"variable": "speed",      "direction": "higher", "low": 1.5, "medium": 2.5, "high": 3.5},
        {"variable": "load",       "direction": "higher", "low": 400, "medium": 700, "high": 900},
        {"variable": "trip_count", "direction": "higher", "low": 10000, "medium": 20000, "high": 30000},
        {"variable": "energy",     "direction": "higher", "low": 8,   "medium": 12,  "high": 15},
        {"variable": "voltage",    "direction": "range",   "low": 200, "medium": None,"high": 240},
        {"variable": "current",    "direction": "higher", "low": 30,  "medium": 40,  "high": 50},
    ]
    for entry in defaults:
        UmbralConfig.objects.update_or_create(
            variable=entry["variable"],
            defaults={
                "direction": entry["direction"],
                "low": entry["low"],
                "medium": entry["medium"],
                "high": entry["high"],
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("front", "0002_umbralconfig"),
    ]

    operations = [
        migrations.RunPython(seed_umbral_config, reverse_code=migrations.RunPython.noop),
    ]
