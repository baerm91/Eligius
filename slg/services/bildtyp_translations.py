"""Permission-bound translation batches. Drafts never write or publish data."""
from slg.models import AvBildtyp, RvBildtyp
from slg.services.editor_api import editor_user
from slg.services.vocabulary_translations import translation_batch, translation_draft


def model_for(user_id, side):
    if side not in ('av', 'rv'):
        raise ValueError('Seite muss av oder rv sein.')
    model = AvBildtyp if side == 'av' else RvBildtyp
    editor_user(user_id, model)
    return model


def get_translation_batch(user_id, side, after_id=0, missing_only=True):
    model = model_for(user_id, side)
    return {'side': side, **translation_batch(model, after_id, missing_only)}


def draft_translations(user_id, side, translations):
    model = model_for(user_id, side)
    return {
        'side': side,
        **translation_draft(model, translations),
        'next_step': 'Review and import this JSON through the matching AvBildtyp/RvBildtyp admin. '
                     'Admin import preview and confirmation are required. No database changes yet.',
    }
