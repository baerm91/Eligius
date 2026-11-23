"""Hintergrund-Abarbeitung großer MTOA-Neuaufbauten.

Ändert sich der Name eines Vokabulars, das an tausenden Objekten hängt (z.B.
Herstellung "Prägung"), dauert der Neuaufbau länger als der Gunicorn-Timeout.
Solche Fälle landen als MtoaSyncAuftrag in der Datenbank und werden nach dem
Commit in einem Hintergrund-Thread abgearbeitet. Der Auftrag bleibt bis zum
Erfolg gespeichert; `manage.py process_mtoa_queue` holt abgebrochene nach.
"""

import logging
import threading
from datetime import timedelta

from django.apps import apps
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Bis zu so vielen Objekten wird direkt im Request synchronisiert.
INLINE_LIMIT = 300
# Ein "in Arbeit"-Auftrag, der so alt ist, gilt als abgebrochen (Worker-Neustart).
STALE_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 5

_worker_lock = threading.Lock()
_worker_running = False


def enqueue(model_label, object_pk):
    """Auftrag speichern und nach dem Commit den Hintergrund-Worker anstoßen."""
    from .models import MtoaSyncAuftrag
    auftrag, created = MtoaSyncAuftrag.objects.get_or_create(
        model_label=model_label, object_pk=object_pk)
    if not created:
        # Erneute Änderung während ein Lauf schon aktiv ist: nochmal von vorn.
        MtoaSyncAuftrag.objects.filter(pk=auftrag.pk).update(
            claimed_at=None, attempts=0, last_error='')
    transaction.on_commit(start_worker)


def start_worker():
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
    threading.Thread(target=_run_worker, name='mtoa-queue', daemon=True).start()


def _run_worker():
    global _worker_running
    try:
        while True:
            try:
                process_queue()
            except Exception:
                logger.exception('MTOA-Warteschlange: Worker-Fehler')
            with _worker_lock:
                # Während des Laufs neu angelegte Aufträge noch mitnehmen;
                # fehlgeschlagene holt der nächste Anstoß bzw. process_mtoa_queue nach.
                if not _has_new_pending():
                    _worker_running = False
                    return
    finally:
        connection.close()
        with _worker_lock:
            _worker_running = False


def _pending_qs():
    from .models import MtoaSyncAuftrag
    from django.db.models import Q
    stale = timezone.now() - STALE_AFTER
    return MtoaSyncAuftrag.objects.filter(
        Q(claimed_at__isnull=True) | Q(claimed_at__lt=stale),
        attempts__lt=MAX_ATTEMPTS,
    )


def _has_new_pending():
    try:
        close_old_connections()
        return _pending_qs().filter(attempts=0).exists()
    except Exception:
        logger.exception('MTOA-Warteschlange: Status nicht lesbar')
        return False


def process_queue(limit=None):
    """Alle fälligen Aufträge abarbeiten. Gibt die Zahl erledigter Aufträge zurück."""
    from .models import MtoaSyncAuftrag
    from .signals import _authority_objects, _sync_queryset

    done = 0
    tried = set()  # pro Durchlauf jeden Auftrag nur einmal versuchen
    while limit is None or done < limit:
        close_old_connections()
        auftrag = _pending_qs().exclude(pk__in=tried).order_by('created_at').first()
        if auftrag is None:
            break
        tried.add(auftrag.pk)
        claimed_at = timezone.now()
        # Atomar beanspruchen, damit parallele Worker nicht doppelt arbeiten.
        claimed = MtoaSyncAuftrag.objects.filter(
            pk=auftrag.pk, claimed_at=auftrag.claimed_at, attempts=auftrag.attempts,
        ).update(claimed_at=claimed_at, attempts=auftrag.attempts + 1)
        if not claimed:
            continue
        try:
            model = apps.get_model(auftrag.model_label)
            instance = model.objects.filter(pk=auftrag.object_pk).first()
            if instance is not None:
                _sync_queryset(_authority_objects(model._meta.model_name, instance))
        except Exception as exc:
            logger.exception('MTOA-Warteschlange: Auftrag %s fehlgeschlagen', auftrag)
            MtoaSyncAuftrag.objects.filter(pk=auftrag.pk, claimed_at=claimed_at).update(
                claimed_at=None, last_error=str(exc)[:2000])
            continue
        # Nur löschen, wenn nicht zwischenzeitlich erneut eingereiht (claimed_at zurückgesetzt).
        MtoaSyncAuftrag.objects.filter(pk=auftrag.pk, claimed_at=claimed_at).delete()
        done += 1
        logger.info('MTOA-Warteschlange: %s erledigt', auftrag)
    return done
