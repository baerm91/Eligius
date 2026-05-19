"""
Django Signals für automatische MTOA-Synchronisation.

Bei jedem Speichern/Löschen von Obj, Muenztyp, Obj_Person oder Mztyp_Person
werden die betroffenen MuenztypObjektAnzeige-Einträge aktualisiert.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_sync_disabled = False


def disable_mtoa_sync():
    """Context-Manager oder Flag zum Deaktivieren des Auto-Syncs (z.B. bei Batch-Import)."""
    global _sync_disabled
    _sync_disabled = True


def enable_mtoa_sync():
    global _sync_disabled
    _sync_disabled = False


def _schedule_sync(obj_ids):
    """Führt den MTOA-Sync für die gegebenen Obj-IDs aus."""
    if _sync_disabled or not obj_ids:
        return
    from .mtoa_sync import sync_objs_to_mtoa
    try:
        sync_objs_to_mtoa(obj_ids)
    except Exception:
        logger.exception("MTOA Auto-Sync fehlgeschlagen für Obj-IDs: %s", obj_ids)


@receiver(post_save, sender='slg.Obj')
def sync_obj_on_save(sender, instance, **kwargs):
    """Einzelnes Objekt nach Speichern synchronisieren."""
    _schedule_sync([instance.pk])


@receiver(post_save, sender='slg.Muenztyp')
def sync_muenztyp_on_save(sender, instance, **kwargs):
    """Alle Objekte dieses Münztyps synchronisieren (max 500 zur Sicherheit)."""
    from .models import Obj
    obj_ids = list(
        Obj.objects.filter(Typ_id=instance.pk).values_list('pk', flat=True)[:500]
    )
    if obj_ids:
        logger.info("Muenztyp %s gespeichert → Sync von %d Objekten", instance.pk, len(obj_ids))
        _schedule_sync(obj_ids)


@receiver(post_save, sender='slg.Slg')
def sync_slg_on_save(sender, instance, **kwargs):
    """Bei Änderungen an Sammlungs-Bildpfaden die betroffenen Objekte neu synchronisieren."""
    from .models import Obj
    obj_ids = list(Obj.objects.filter(Slg_id=instance.pk).values_list('pk', flat=True)[:2000])
    if obj_ids:
        logger.info("Slg %s gespeichert → Sync von %d Objekten", instance.pk, len(obj_ids))
        _schedule_sync(obj_ids)


@receiver(post_save, sender='slg.SlgTeil')
def sync_slgteil_on_save(sender, instance, **kwargs):
    """Bei Änderungen am Sammlungsteil ebenfalls Thumbnail-/Bildpfade neu synchronisieren."""
    from .models import Obj
    obj_ids = list(Obj.objects.filter(SlgTeil_id=instance.pk).values_list('pk', flat=True)[:2000])
    if obj_ids:
        logger.info("SlgTeil %s gespeichert → Sync von %d Objekten", instance.pk, len(obj_ids))
        _schedule_sync(obj_ids)


@receiver(post_save, sender='slg.Obj_Person')
@receiver(post_delete, sender='slg.Obj_Person')
def sync_obj_person_change(sender, instance, **kwargs):
    """Objekt synchronisieren wenn Obj_Person geändert/gelöscht wird."""
    obj_id = instance.idfk_Obj_id
    if obj_id:
        _schedule_sync([obj_id])


@receiver(post_save, sender='slg.Mztyp_Person')
@receiver(post_delete, sender='slg.Mztyp_Person')
def sync_mztyp_person_change(sender, instance, **kwargs):
    """Alle Objekte des Münztyps synchronisieren wenn Mztyp_Person geändert/gelöscht wird."""
    from .models import Obj
    mztyp_id = instance.Mztyp_id
    if mztyp_id:
        obj_ids = list(
            Obj.objects.filter(Typ_id=mztyp_id).values_list('pk', flat=True)
        )
        if obj_ids:
            _schedule_sync(obj_ids)
