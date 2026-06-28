from django import template
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

register = template.Library()


@register.filter
def naturaltime_es(value):
    if value is None:
        return ""

    now = timezone.localtime(timezone.now())
    if timezone.is_naive(value):
        value = timezone.make_aware(value)

    delta = now - value

    if delta.total_seconds() < 60:
        return "Ahora"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() // 60)
        return "Hace 1 min" if minutes == 1 else f"Hace {minutes} min"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() // 3600)
        return "Hace 1 h" if hours == 1 else f"Hace {hours} h"
    elif delta.total_seconds() < 2592000:
        days = int(delta.total_seconds() // 86400)
        return "Hace 1 d" if days == 1 else f"Hace {days} d"
    else:
        return date_filter(value, "d/m/Y")
