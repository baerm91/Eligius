"""Staff tools for enriching spreadsheet data."""

import logging
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect, render
from django.utils.http import content_disposition_header

from ..export_safety import neutralize_formula
from ..models import Muenztyp

logger = logging.getLogger(__name__)


EXCEL_ENRICH_MAX_UPLOAD = 10 * 1024 * 1024          # 10 MB Datei
EXCEL_ENRICH_MAX_UNCOMPRESSED = 100 * 1024 * 1024   # 100 MB entpackt (ZIP-Bomben)


def _xlsx_too_large(uploaded):
    import zipfile
    if uploaded.size > EXCEL_ENRICH_MAX_UPLOAD:
        return True
    try:
        with zipfile.ZipFile(uploaded) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        return False  # openpyxl meldet das Format sauber als Fehler
    finally:
        uploaded.seek(0)
    return total > EXCEL_ENRICH_MAX_UNCOMPRESSED


@staff_member_required
@permission_required('slg.view_muenztyp', raise_exception=True)
def excel_ocre_enrich(request):
    import io

    import openpyxl
    from django.http import HttpResponse

    if request.method == 'POST':
        if 'excel_file' not in request.FILES or not request.POST.get('ocre_column'):
            messages.error(request, 'Bitte eine Datei hochladen und den Spaltennamen für die OCRE-Links angeben.')
            return redirect('excel_ocre_enrich')

        excel_file = request.FILES['excel_file']
        ocre_column_name = request.POST.get('ocre_column').strip()
        if _xlsx_too_large(excel_file):
            messages.error(request, 'Die Datei ist zu groß (max. 10 MB, entpackt 100 MB).')
            return redirect('excel_ocre_enrich')

        try:
            wb = openpyxl.load_workbook(excel_file)
            sheet = wb.active

            # Find the OCRE column index (case-insensitive and ignoring extra spaces)
            # Nur die erste Zeile lesen (list(sheet.rows) lädt das ganze Blatt).
            header_row = next(sheet.iter_rows(min_row=1, max_row=1), None)
            if not header_row:
                messages.error(request, 'Die Tabelle ist leer.')
                return redirect('excel_ocre_enrich')
            ocre_col_idx = None
            for idx, cell in enumerate(header_row):
                if cell.value and str(cell.value).strip().lower() == ocre_column_name.lower():
                    ocre_col_idx = idx
                    break

            if ocre_col_idx is None:
                messages.error(request, f'Spalte "{ocre_column_name}" nicht gefunden.')
                return redirect('excel_ocre_enrich')

            # Fetch all MuenzTyp data into a dictionary for fast lookup to avoid N queries
            all_types = Muenztyp.objects.exclude(link__isnull=True).exclude(link="").select_related(
                'av_bildtyp', 'rv_bildtyp', 'workflow'
            ).only(
                'link', 'avbeschr', 'rvbeschr', 'av_bildtyp__name', 'rv_bildtyp__name', 'workflow__name', 'muenztyptitel'
            )

            id_to_data = {}
            for t in all_types:
                if t.link and '/id/' in t.link:
                    extracted_id = t.link.split('/id/')[-1].strip('/').lower()

                    # Get AV and RV Descriptions from AvBildtyp/RvBildtyp (fallback to avbeschr/rvbeschr if necessary)
                    av_text = t.av_bildtyp.name if t.av_bildtyp else (t.avbeschr or "")
                    rv_text = t.rv_bildtyp.name if t.rv_bildtyp else (t.rvbeschr or "")

                    id_to_data[extracted_id] = {
                        'av': av_text,
                        'rv': rv_text,
                        'wf': t.workflow.name if t.workflow else "",
                        'titel': t.muenztyptitel or ""
                    }

            # Add new headers
            max_col = sheet.max_column
            col_avbeschr = max_col + 1
            col_rvbeschr = max_col + 2
            col_workflow = max_col + 3
            col_titel = max_col + 4

            sheet.cell(row=1, column=col_avbeschr, value="Av-Beschreibung")
            sheet.cell(row=1, column=col_rvbeschr, value="Rv-Beschreibung")
            sheet.cell(row=1, column=col_workflow, value="Workflow")
            sheet.cell(row=1, column=col_titel, value="Münztyptitel")

            # Process rows using the cached map
            for row_idx in range(2, sheet.max_row + 1):
                ocre_link_cell = sheet.cell(row=row_idx, column=ocre_col_idx + 1)
                link_val = ocre_link_cell.value

                if link_val:
                    # Extract the ID from the link, assuming format like http://numismatics.org/ocre/id/ric.1(2).aug.1A
                    link_str = str(link_val).strip()
                    if '/id/' in link_str:
                        extracted_id = link_str.split('/id/')[-1].strip('/').lower()

                        data = id_to_data.get(extracted_id)

                        if data:
                            sheet.cell(row=row_idx, column=col_avbeschr, value=neutralize_formula(data['av']))
                            sheet.cell(row=row_idx, column=col_rvbeschr, value=neutralize_formula(data['rv']))
                            sheet.cell(row=row_idx, column=col_workflow, value=neutralize_formula(data['wf']))
                            sheet.cell(row=row_idx, column=col_titel, value=neutralize_formula(data['titel']))

            # Save to memory and return
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)

            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            # Hochgeladener Dateiname ist Nutzereingabe: Steuerzeichen, Anführungs-
            # zeichen und Pfadtrenner entfernen (Header-Injection/BadHeaderError).
            original_name = re.sub(r'[\x00-\x1f\x7f"\\/]', '_', excel_file.name or '').strip() or 'datei.xlsx'
            new_name = original_name.replace('.xlsx', '_angereichert.xlsx') if '.xlsx' in original_name else f'{original_name}_angereichert.xlsx'
            response['Content-Disposition'] = content_disposition_header(True, new_name)
            return response

        except Exception:
            logger.exception('Fehler bei Excel-Verarbeitung')
            messages.error(request, 'Die Datei konnte nicht verarbeitet werden. Bitte eine gültige .xlsx-Datei hochladen.')
            return redirect('excel_ocre_enrich')

    return render(request, 'slg/excel_ocre_enrich.html')
