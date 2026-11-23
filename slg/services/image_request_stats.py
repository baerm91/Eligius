from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

ORIGINS = ('Kulturpool', 'Europeana', 'Eligius', 'Direkt / unbekannt', 'Andere')


def origin_group(host):
    if not host:
        return 'Direkt / unbekannt'
    if host == 'eligius':
        return 'Eligius'
    for domain, name in (('kulturpool.at', 'Kulturpool'), ('europeana.eu', 'Europeana')):
        if host == domain or host.endswith('.' + domain):
            return name
    return 'Andere'


def summarize_image_requests(queryset, *, has_selected_date=False, monthly=False):
    period = None
    bucket = 'datum'
    if monthly:
        queryset = queryset.annotate(month=TruncMonth('datum'))
        bucket = 'month'
    elif not has_selected_date:
        end = timezone.localdate()
        start = end - timedelta(days=29)
        period = (start, end)
        queryset = queryset.filter(datum__range=period)

    by_origin = {origin: [0, 0] for origin in ORIGINS}
    timeline = {}
    entries = queryset.order_by().values(bucket, 'herkunft', 'automatisiert').annotate(total=Sum('anzahl'))
    for row in entries:
        kind = int(row['automatisiert'])
        by_origin[origin_group(row['herkunft'])][kind] += row['total']
        timeline.setdefault(row[bucket], [0, 0])[kind] += row['total']
    if period:
        for days in range(30):
            timeline.setdefault(period[0] + timedelta(days=days), [0, 0])
    peak = max((sum(counts) for counts in timeline.values()), default=0)
    top = queryset.filter(automatisiert=False).order_by().values(
        'obj_id', 'obj__invnr', 'obj__Slg__name',
    ).annotate(total=Sum('anzahl')).order_by('-total', 'obj_id')[:10]
    return {
        'period': period, 'monthly': monthly, 'peak': peak,
        'timeline': sorted(timeline.items()), 'origins': by_origin.items(), 'top': list(top),
        'total': sum(sum(pair) for pair in by_origin.values()),
    }
