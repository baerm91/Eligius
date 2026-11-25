from django.test import TestCase
from rest_framework.test import APIClient

from slg.models import Workflow, Obj, MuenztypObjektAnzeige
from slg.test_editor_mcp import fixtures


class CitationGroupTests(TestCase):
    def test_only_open_matching_objects_are_assigned_and_retry_is_safe(self):
        user, typ, obj, classified, _ = fixtures()
        workflow = Workflow.objects.create(name="kontrolliert", reihenfolge=3)
        protected = Obj.objects.create(invnr="E-3", Slg=obj.Slg, Objekttyp=None, workflow=workflow)
        members = [{"id": row.pk, "inv": row.invnr} for row in (obj, classified, protected)]
        client = APIClient()
        client.force_authenticate(user)
        path = "/api/objekte/zitatgruppe/"
        data = {"type": typ.pk, "members": members}
        self.assertEqual(client.post(path, data, format="json").status_code, 403)
        user.is_staff = True
        user.save()
        result = client.post(path, data, format="json")
        self.assertEqual(result.data, {"assigned": 1, "skipped": 2})
        obj.refresh_from_db()
        protected.refresh_from_db()
        self.assertEqual(obj.Typ_id, typ.pk)
        self.assertIsNone(protected.Typ_id)
        self.assertTrue(MuenztypObjektAnzeige.objects.filter(obj_id=obj.pk).exists())
        self.assertEqual(client.post(path, data, format="json").data, {"assigned": 0, "skipped": 3})
