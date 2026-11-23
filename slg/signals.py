"""
Django Signals für automatische MTOA-Synchronisation.

Bei jedem Speichern/Löschen von Obj, Muenztyp, Obj_Person, Mztyp_Person und
den in der MTOA angezeigten Vokabularen werden die betroffenen
MuenztypObjektAnzeige-Einträge aktualisiert bzw. entfernt.

Hinweis: QuerySet.update()/bulk_update() lösen keine Signals aus. Code, der so
massenhaft ändert, ruft danach sync_queryset_to_mtoa() bzw. sync_objs_to_mtoa().
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models import Q
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete, m2m_changed
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

# Pro Request/Thread (ContextVar statt Modul-Global): parallele Requests
# überspringen so keine Syncs mehr. Zähler, damit verschachtelte Pausen
# korrekt aufgelöst werden.
_sync_pause_depth = ContextVar('mtoa_sync_pause_depth', default=0)


def disable_mtoa_sync():
    """Auto-Sync im aktuellen Kontext pausieren (z.B. bei Batch-Import).

    Immer mit enable_mtoa_sync() in einem finally kombinieren oder
    besser mtoa_sync_paused() verwenden.
    """
    _sync_pause_depth.set(_sync_pause_depth.get() + 1)


def enable_mtoa_sync():
    _sync_pause_depth.set(max(0, _sync_pause_depth.get() - 1))


def mtoa_sync_is_disabled():
    return _sync_pause_depth.get() > 0


@contextmanager
def mtoa_sync_paused():
    disable_mtoa_sync()
    try:
        yield
    finally:
        enable_mtoa_sync()


def _schedule_sync(obj_ids):
    """Führt den MTOA-Sync für die gegebenen Obj-IDs aus."""
    if mtoa_sync_is_disabled() or not obj_ids:
        return
    from .mtoa_sync import sync_objs_to_mtoa
    try:
        sync_objs_to_mtoa(obj_ids)
    except Exception:
        logger.exception("MTOA Auto-Sync fehlgeschlagen für Obj-IDs: %s", obj_ids)


def _sync_ids(obj_ids):
    obj_ids = list(obj_ids)
    for start in range(0, len(obj_ids), 500):
        _schedule_sync(obj_ids[start:start + 500])


def _sync_queryset(objects):
    """Bounded batches, without silently dropping objects beyond a fixed limit."""
    if mtoa_sync_is_disabled():
        return
    batch = []
    for obj_id in objects.order_by('pk').values_list('pk', flat=True).distinct().iterator(chunk_size=500):
        batch.append(obj_id)
        if len(batch) == 500:
            _schedule_sync(batch)
            batch = []
    _schedule_sync(batch)


def sync_queryset_to_mtoa(objects):
    """Öffentliche Variante für Bulk-Änderungen (.update()/.bulk_update())."""
    _sync_queryset(objects)


@receiver(post_save, sender='slg.Obj')
def sync_obj_on_save(sender, instance, **kwargs):
    """Einzelnes Objekt nach Speichern synchronisieren."""
    if not kwargs.get('raw'):
        _schedule_sync([instance.pk])


@receiver(post_delete, sender='slg.Obj')
def remove_obj_projection(sender, instance, **kwargs):
    """Gelöschte Münzen sofort aus der MTOA entfernen (sonst 404-Geister in /browse/)."""
    from .models import MuenztypObjektAnzeige
    try:
        MuenztypObjektAnzeige.objects.filter(obj_id=instance.pk).delete()
        from .mtoa_sync import _invalidate_browse_cache
        _invalidate_browse_cache()
    except Exception:
        logger.exception("MTOA-Eintrag für gelöschtes Obj %s konnte nicht entfernt werden", instance.pk)


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
    if instance.pk and not mtoa_sync_is_disabled() and not kwargs.get('raw'):
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


@receiver(pre_save, sender='slg.AvBildtyp_Schlagwort')
@receiver(pre_save, sender='slg.RvBildtyp_Schlagwort')
def remember_previous_bildtyp(sender, instance, **kwargs):
    if instance.pk and not mtoa_sync_is_disabled() and not kwargs.get('raw'):
        field = 'avbildtyp_id' if sender._meta.model_name == 'avbildtyp_schlagwort' else 'rvbildtyp_id'
        instance._mtoa_previous_bildtyp = sender.objects.filter(pk=instance.pk).values_list(field, flat=True).first()


@receiver(post_save, sender='slg.AvBildtyp_Schlagwort')
@receiver(post_delete, sender='slg.AvBildtyp_Schlagwort')
@receiver(post_save, sender='slg.RvBildtyp_Schlagwort')
@receiver(post_delete, sender='slg.RvBildtyp_Schlagwort')
def sync_bildtyp_schlagwort_change(sender, instance, **kwargs):
    """Schlagwort-Zuordnung eines Bildtyps: av_/rv_schlagworte der MTOA neu aufbauen."""
    from .models import Obj
    if kwargs.get('raw') or mtoa_sync_is_disabled():
        return
    side = 'av' if sender._meta.model_name == 'avbildtyp_schlagwort' else 'rv'
    ids = {pk for pk in (getattr(instance, f'{side}bildtyp_id'), getattr(instance, '_mtoa_previous_bildtyp', None)) if pk}
    _sync_queryset(Obj.objects.filter(
        Q(**{f'{side}_bildtyp_id__in': ids}) | Q(**{f'Typ__{side}_bildtyp_id__in': ids})))


# Extend the existing projection updater to the authority data used by EDM.
AUTHORITY_MODELS = (
    'slg.Person', 'slg.PersonFunktion', 'slg.Metall', 'slg.Nominal', 'slg.Mzstaette',
    'slg.Region', 'slg.Objekttyp', 'slg.Herstellung', 'slg.Workflow', 'slg.AvBildtyp',
    'slg.RvBildtyp', 'slg.AvBeizeichen', 'slg.RvBeizeichen', 'slg.AvOffizin', 'slg.RvOffizin',
    # Ebenfalls als Text in der MTOA (Anzeige/Facetten):
    'slg.Schlagwort', 'slg.Reichskreis', 'slg.Muenzstand',
    'slg.AvBildrand', 'slg.RvBildrand', 'slg.Rand',
)

# model_name -> (FK am Obj, FK am Muenztyp oder None)
_AUTHORITY_FIELDS = {
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
    'reichskreis': (None, 'Reichskreis_id'),
    'muenzstand': ('idfk_Muenzstand_id', 'Muenzstand_id'),
    'avbildrand': ('av_bildrand_id', 'av_bildrand_id'),
    'rvbildrand': ('rv_bildrand_id', 'rv_bildrand_id'),
    'rand': ('rand_id', 'rand_id'),
}


def _authority_objects(name, instance):
    """Alle Objekte, deren MTOA-Zeile dieses Vokabular anzeigt."""
    from .models import Obj, Obj_Person, Mztyp_Person, AvBildtyp_Schlagwort, RvBildtyp_Schlagwort
    if name in ('person', 'personfunktion'):
        field = 'idfk_Person_id' if name == 'person' else 'idfk_PersonFunktion_id'
        return Obj.objects.filter(
            Q(pk__in=Obj_Person.objects.filter(**{field: instance.pk}).values('idfk_Obj_id')) |
            Q(Typ_id__in=Mztyp_Person.objects.filter(**{field: instance.pk}).values('Mztyp_id'))
        )
    if name == 'schlagwort':
        av_ids = AvBildtyp_Schlagwort.objects.filter(schlagwort_id=instance.pk).values('avbildtyp_id')
        rv_ids = RvBildtyp_Schlagwort.objects.filter(schlagwort_id=instance.pk).values('rvbildtyp_id')
        return Obj.objects.filter(
            Q(av_bildtyp_id__in=av_ids) | Q(Typ__av_bildtyp_id__in=av_ids) |
            Q(rv_bildtyp_id__in=rv_ids) | Q(Typ__rv_bildtyp_id__in=rv_ids)
        )
    own, inherited = _AUTHORITY_FIELDS[name]
    condition = Q(pk__in=[])
    if own:
        condition |= Q(**{own: instance.pk})
    if inherited:
        condition |= Q(**{'Typ__' + inherited: instance.pk})
    if name == 'workflow':
        condition |= Q(Typ__Konkordanz__workflow_id=instance.pk)
    return Obj.objects.filter(condition)


def sync_authority_change(sender, instance, **kwargs):
    if mtoa_sync_is_disabled() or kwargs.get('raw'):
        return
    if kwargs.get('update_fields') == {'name_en'}:
        # English labels are read from the vocabulary, not the object projection,
        # but they are part of the EDM export: only advance the OAI datestamp.
        from .models import MuenztypObjektAnzeige
        MuenztypObjektAnzeige.objects.filter(
            obj_id__in=_authority_objects(sender._meta.model_name, instance).values('pk'),
        ).update(last_modified=timezone.now())
        return
    _sync_queryset(_authority_objects(sender._meta.model_name, instance))


def remember_authority_objects(sender, instance, **kwargs):
    """Vor dem Löschen merken, welche Objekte betroffen sind (danach ist die Zuordnung weg)."""
    if mtoa_sync_is_disabled():
        return
    instance._mtoa_affected_objects = list(
        _authority_objects(sender._meta.model_name, instance).values_list('pk', flat=True).distinct())


def sync_authority_delete(sender, instance, **kwargs):
    _sync_ids(getattr(instance, '_mtoa_affected_objects', []))


for _label in AUTHORITY_MODELS:
    post_save.connect(sync_authority_change, sender=_label, dispatch_uid=f'mtoa-save-{_label}')
    pre_delete.connect(remember_authority_objects, sender=_label, dispatch_uid=f'mtoa-predelete-{_label}')
    post_delete.connect(sync_authority_delete, sender=_label, dispatch_uid=f'mtoa-delete-{_label}')


@receiver(pre_delete, sender='slg.Muenztyp')
def remember_muenztyp_objects(sender, instance, **kwargs):
    from .models import Obj
    if not mtoa_sync_is_disabled():
        instance._mtoa_affected_objects = list(
            Obj.objects.filter(Q(Typ_id=instance.pk) | Q(Typ__Konkordanz=instance))
            .values_list('pk', flat=True).distinct())


@receiver(post_delete, sender='slg.Muenztyp')
def sync_muenztyp_delete(sender, instance, **kwargs):
    _sync_ids(getattr(instance, '_mtoa_affected_objects', []))


def sync_concordance_change(sender, instance, action, pk_set, **kwargs):
    if mtoa_sync_is_disabled():
        return
    from .models import Obj
    if action == 'pre_clear':
        instance._mtoa_cleared_concordances = list(instance.Konkordanz.values_list('pk', flat=True))
    elif action in ('post_add', 'post_remove', 'post_clear'):
        ids = {instance.pk} | set(pk_set or getattr(instance, '_mtoa_cleared_concordances', []))
        _sync_queryset(Obj.objects.filter(Typ_id__in=ids))


from .models import Muenztyp
m2m_changed.connect(sync_concordance_change, sender=Muenztyp.Konkordanz.through)
