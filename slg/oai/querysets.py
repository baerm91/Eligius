"""Bounded projection reads with permission checks on the canonical objects."""
from django.db.models import Exists, OuterRef, Prefetch, Q, Subquery

from slg.models import MtoaPerson, Muenztyp, MuenztypObjektAnzeige, Obj, Obj_Ref

CONTROLLED = 'kontrolliert'


def eligible_objects():
    # Both models use workflow.name='kontrolliert' (also used by Nomisma).
    # Obj.freigabe is historically unused and is not a quality/release status.
    return Obj.objects.filter(
        Slg__kulturpool_export_erlaubt=True,
        workflow__name__iexact=CONTROLLED,
    ).filter(Q(Typ__isnull=True) | Q(Typ__workflow__name__iexact=CONTROLLED))


def export_rows():
    canonical = eligible_objects().filter(pk=OuterRef('obj_id'), Slg_id=OuterRef('slg_fk_id'))
    # Fail closed if an old projection still describes a different coin type.
    typed = canonical.filter(Typ_id=OuterRef('typ_fk_id'), Typ__isnull=False)
    untyped = eligible_objects().filter(pk=OuterRef('obj_id'), Slg_id=OuterRef('slg_fk_id'), Typ__isnull=True)
    latest = MuenztypObjektAnzeige.objects.filter(obj_id=OuterRef('obj_id')).order_by('-pk')
    return MuenztypObjektAnzeige.objects.filter(last_modified__isnull=False).alias(
        allowed_typed=Exists(typed), allowed_untyped=Exists(untyped),
    ).filter(Q(allowed_typed=True) | Q(typ_fk__isnull=True, allowed_untyped=True)).filter(
        pk=Subquery(latest.values('pk')[:1])
    ).order_by('obj_id')


def with_metadata_relations(rows):
    return rows.select_related(
        'slg_fk', 'slgteil_fk', 'slgteil_fk__idfk_Slg_SlgTeil',
        'nominal_fk', 'metall_fk', 'mzstaette_fk', 'region_fk',
        'objekttyp_fk', 'herstellung_fk',
    ).prefetch_related(Prefetch(
        'mtoaperson_set', queryset=MtoaPerson.objects.select_related('person', 'funktion').order_by('pk'),
    ))


def objects_for_rows(rows):
    """One page-local join, because MTOA.obj_id is an integer, not a ForeignKey."""
    concordances = Muenztyp.objects.filter(workflow__name__iexact=CONTROLLED).only('pk', 'link')
    objects = eligible_objects().filter(pk__in=[row.obj_id for row in rows]).select_related(
        'Slg', 'Typ',
    ).only(
        'pk', 'Slg', 'Typ',
        'Slg__name', 'Slg__bildrechte_lizenz', 'Slg__kulturpool_rights_uri',
        'Slg__kulturpool_metadata_rights_uri', 'Slg__nomisma_collection_uri',
        'Typ__link',
    ).prefetch_related(
        Prefetch('obj_ref_set', queryset=Obj_Ref.objects.only('pk', 'idfk_Obj_id', 'link')),
        Prefetch('Typ__Konkordanz', queryset=concordances),
    )
    return {obj.pk: obj for obj in objects}
