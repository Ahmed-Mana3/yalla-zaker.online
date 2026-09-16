from django import template

register = template.Library()


@register.filter
def dur(seconds):
    """Seconds -> human readable: 92 -> '1m 32s', 5400 -> '1h 30m'."""
    if seconds is None:
        seconds = 0
    seconds = int(seconds)
    hh, rem = divmod(seconds, 3600)
    mm, ss = divmod(rem, 60)
    if hh:
        return f'{hh}h {mm}m'
    if mm:
        return f'{mm}m {ss}s' if ss else f'{mm}m'
    return f'{ss}s'


@register.filter
def hours(num):
    """Float hours -> '12.5h'."""
    if num is None:
        num = 0
    return f'{num:g}h'


@register.filter
def split(value, sep=' '):
    """Split a string into a list for {% for %} loops: '25 45 60' -> ['25','45','60']."""
    return [x for x in str(value).split(sep) if x]


@register.filter
def mmss(minutes):
    """Minutes -> clock 'mm:ss' for the lamp: 45 -> '45:00'."""
    if not minutes:
        return '00:00'
    total = int(minutes) * 60
    return f'{total // 60:02d}:{total % 60:02d}'


@register.filter
def hours_val(seconds):
    """Seconds -> float hours rounded to 2 decimals, minimum 0.0: e.g. 5400 -> 1.5."""
    if not seconds:
        return 0.0
    return round(int(seconds) / 3600, 2)


@register.filter
def round2(num):
    """Round a number to 2 decimal places: 1.25000 -> 1.25."""
    if num is None:
        return 0
    try:
        val = float(num)
        return f'{val:g}'
    except (ValueError, TypeError):
        return num