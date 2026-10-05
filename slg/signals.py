"""
Django Signals für automatische MTOA-Synchronisation.

Bei jedem Speichern/Löschen von Obj, Muenztyp, Obj_Person oder Mztyp_Person
werden die betroffenen MuenztypObjektAnzeige-Einträge aktualisiert.
"""

import logging
from django.db.models import Q
from django.db.models.signals import pre_save, post_save, post_delete, m2m_changed
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


def _sync_queryset(objects):
    """Bounded batches, without silently dropping objects beyond a fixed limit."""
    if _sync_disabled:
        return
    batch = []
    for obj_id in objects.order_by('pk').values_list('pk', flat=True).distinct().iterator(chunk_size=500):
        batch.append(obj_id)
        if len(batch) == 500:
            _schedule_sync(batch)
            batch = []
    _schedule_sync(batch)


@receiver(post_save, sender='slg.Obj')
def sync_obj_on_save(sender, instance, **kwargs):
    """Einzelnes Objekt nach Speichern synchronisieren."""
    if not kwargs.get('raw'):
        _schedule_sync([instance.pk])


@receiver(post_save, sender='slg.Muenztyp')
def sync_muenztyp_on_save(sender, instance, **kwargs):
    """Alle Objekte und exportrelevanten Konkordanzen dieses Münztyps synchronisieren."""
    from .models import Obj
    if not kwargs.get('raw'):
        _sync_queryset(Obj.objects.filter(Q(Typ_id=instance.pk) | Q(Typ__Konkordanz=instance)))


@receiver(post_save, sender='slg.Slg')
def sync_slg_on_save(sender, instance, **kwargs):
    """Bei Änderungen an Sammlungs-Bildpfaden die betroffenen Objekte neu synchronisieren."""
    from .models import Obj
    if not kwargs.get('raw'):
        _sync_queryset(Obj.objects.filter(Q(Slg_id=instance.pk) | Q(SlgTeil__idfk_Slg_SlgTeil_id=instance.pk)))


@receiver(post_save, sender='slg.SlgTeil')
def sync_slgteil_on_save(sender, instance, **kwargs):
    """Bei Änderungen am Sammlungsteil ebenfalls Thumbnail-/Bildpfade neu synchronisieren."""
    from .models import Obj
    if not kwargs.get('raw'):
        _sync_queryset(Obj.objects.filter(SlgTeil_id=instance.pk))


@receiver(pre_save, sender='slg.Obj_Person')
@receiver(pre_save, sender='slg.Mztyp_Person')
@receiver(pre_save, sender='slg.Obj_Ref')
def remember_previous_owner(sender, instance, **kwargs):
    if instance.pk and not _sync_disabled and not kwargs.get('raw'):
        field = 'Mztyp_id' if sender._meta.model_name == 'mztyp_person' else 'idfk_Obj_id'
        instance._mtoa_previous_owner = sender.objects.filter(pk=instance.pk).values_list(field, flat=True).first()


@receiver(post_save, sender='slg.Obj_Person')
@receiver(post_delete, sender='slg.Obj_Person')
@receiver(post_save, sender='slg.Obj_Ref')
@receiver(post_delete, sender='slg.Obj_Ref')
def sync_obj_person_change(sender, instance, **kwargs):
    """Auch öffentliche Typologiereferenzen und frühere Zuordnungen aktualisieren."""
    if not kwargs.get('raw'):
        _schedule_sync(list({pk for pk in (instance.idfk_Obj_id, getattr(instance, '_mtoa_previous_owner', None)) if pk}))


@receiver(post_save, sender='slg.Mztyp_Person')
@receiver(post_delete, sender='slg.Mztyp_Person')
def sync_mztyp_person_change(sender, instance, **kwargs):
    """Alle Objekte des Münztyps synchronisieren wenn Mztyp_Person geändert/gelöscht wird."""
    from .models import Obj
    if not kwargs.get('raw'):
        ids = [pk for pk in (instance.Mztyp_id, getattr(instance, '_mtoa_previous_owner', None)) if pk]
        _sync_queryset(Obj.objects.filter(Typ_id__in=ids))


# Extend the existing projection updater to the authority data used by EDM.
@receiver(post_save, sender='slg.Person')
@receiver(post_save, sender='slg.PersonFunktion')
@receiver(post_save, sender='slg.Metall')
@receiver(post_save, sender='slg.Nominal')
@receiver(post_save, sender='slg.Mzstaette')
@receiver(post_save, sender='slg.Region')
@receiver(post_save, sender='slg.Objekttyp')
@receiver(post_save, sender='slg.Herstellung')
@receiver(post_save, sender='slg.Workflow')
@receiver(post_save, sender='slg.AvBildtyp')
@receiver(post_save, sender='slg.RvBildtyp')
@receiver(post_save, sender='slg.AvBeizeichen')
@receiver(post_save, sender='slg.RvBeizeichen')
@receiver(post_save, sender='slg.AvOffizin')
@receiver(post_save, sender='slg.RvOffizin')
def sync_authority_change(sender, instance, **kwargs):
    if _sync_disabled or kwargs.get('raw'):
        return
    from .models import Obj, Obj_Person, Mztyp_Person
    name = sender._meta.model_name
    if name in ('person', 'personfunktion'):
        field = 'idfk_Person_id' if name == 'person' else 'idfk_PersonFunktion_id'
        objects = Obj.objects.filter(
            Q(pk__in=Obj_Person.objects.filter(**{field: instance.pk}).values('idfk_Obj_id')) |
            Q(Typ_id__in=Mztyp_Person.objects.filter(**{field: instance.pk}).values('Mztyp_id'))
        )
    else:
        own, inherited = {
            'metall': ('Metall_id', 'Metall_id'),
            'nominal': ('idfk_Nominal_id', 'Nominal_id'),
            'mzstaette': ('idfk_Mzstaette_id', 'Mzstaette_id'),
            'region': ('region_id', 'region_id'),
            'objekttyp': ('Objekttyp_id', 'Objekttyp_id'),
            'herstellung': ('idfk_Herstellung_id', 'Herstellung_id'),
            'workflow': ('workflow_id', 'workflow_id'),
            'avbildtyp': ('av_bildtyp_id', 'av_bildtyp_id'),
            'rvbildtyp': ('rv_bildtyp_id', 'rv_bildtyp_id'),
            'avbeizeichen': ('av_beizeichen_id', 'av_beizeichen_id'),
            'rvbeizeichen': ('rv_beizeichen_id', 'rv_beizeichen_id'),
            'avoffizin': ('av_offizin_id', None),
            'rvoffizin': ('rv_offizin_id', None),
        }[name]
        condition = Q(**{own: instance.pk})
        if inherited:
            condition |= Q(**{'Typ__' + inherited: instance.pk})
        if name == 'workflow':
            condition |= Q(Typ__Konkordanz__workflow_id=instance.pk)
        objects = Obj.objects.filter(condition)
    _sync_queryset(objects)


def sync_concordance_change(sender, instance, action, pk_set, **kwargs):
    if _sync_disabled:
        return
    from .models import Obj
    if action == 'pre_clear':
        instance._mtoa_cleared_concordances = list(instance.Konkordanz.values_list('pk', flat=True))
    elif action in ('post_add', 'post_remove', 'post_clear'):
        ids = {instance.pk} | set(pk_set or getattr(instance, '_mtoa_cleared_concordances', []))
        _sync_queryset(Obj.objects.filter(Typ_id__in=ids))


from .models import Muenztyp
m2m_changed.connect(sync_concordance_change, sender=Muenztyp.Konkordanz.through)
