# URL -> View -> Template map

| URL | View | Template(s) | Source |
|---|---|---|---|
| `/about/` | `about` | `slg/about.html ` | `djangoproject/urls.py` |
| `/admin/` | `admin.site.urls` | `- ` | `djangoproject/urls.py` |
| `/slg/<int:id>/` | `SammlungView` | `slg/Sammlung.html ` | `djangoproject/urls.py` |
| `/objekt/<int:id>/` | `ObjektView` | `slg/details.html ` | `djangoproject/urls.py` |
| `/typ/<int:id>/` | `TypView` | `slg/typ_detail.html ` | `djangoproject/urls.py` |
| `/av_schlagwort/<int:id>/` | `AvSchlagwortView` | `slg/avschlagwort_detail.html ` | `djangoproject/urls.py` |
| `/rv_schlagwort/<int:id>/` | `RvSchlagwortView` | `slg/rvschlagwort_detail.html ` | `djangoproject/urls.py` |
| `/rv_schlagwort/<int:id>/timeline` | `RvSchlagwortTimelineView` | `slg/timeline_bildtypen.html ` | `djangoproject/urls.py` |
| `/person/<int:id>/timeline` | `PraegeherrTimelineView` | `slg/timeline_praegeherr.html ` | `djangoproject/urls.py` |
| `/person/<int:id>/modal/` | `PersonModalView` | `slg/modal_person.html ` | `djangoproject/urls.py` |
| `/nominal/<int:id>/modal/` | `NominalModalView` | `slg/modal_nominal.html ` | `djangoproject/urls.py` |
| `/id/<int:id>/update/` | `MzUpdate` | `slg/obj_form.html ` | `djangoproject/urls.py` |
| `/id/<int:pk>/edit/` | `ObjUpdateView.as_view(` | `slg/update_obj.html ` | `djangoproject/urls.py` |
| `/create/` | `ObjCreateView.as_view(` | `slg/create_object.html ` | `djangoproject/urls.py` |
| `/id/<int:id>.ttl` | `rdfliboutput` | `- ` | `djangoproject/urls.py` |
| `/browse/` | `cache_page(60 * 5` | `- ` | `djangoproject/urls.py` |
| `/browse_legacy/` | `cache_page(60 * 5` | `- ` | `djangoproject/urls.py` |
| `/` | `include('slg.urls'` | `- ` | `djangoproject/urls.py` |
| `/api/objekt/<str:invnr>/` | `ObjektDetail.as_view(` | `- ` | `djangoproject/urls.py` |
| `/api/` | `include('slg.urls'` | `- ` | `djangoproject/urls.py` |
| `/select2/` | `include('django_select2.urls'` | `- ` | `djangoproject/urls.py` |
| `/adminactions/` | `include('adminactions.urls'` | `- ` | `djangoproject/urls.py` |
| `/ajax/get-konkordanzen/` | `get_konkordanzen` | `- ` | `djangoproject/urls.py` |
| `/export-obj-lsno/` | `ExportObjLSNO.as_view(` | `- ` | `djangoproject/urls.py` |
| `/export_xlsx/` | `export_xlsx` | `- ` | `djangoproject/urls.py` |
| `/objekt_detail_partial/` | `objekt_detail_partial` | `objekt_detail_partial.html ` | `djangoproject/urls.py` |
| `/__debug__/` | `include(debug_toolbar.urls` | `- ` | `djangoproject/urls.py` |
| `/` | `cache_page(60 * 5` | `- ` | `slg/urls.py` |
| `/about/` | `cache_page(60 * 30` | `- ` | `slg/urls.py` |
| `/api-token-auth/` | `api_views.obtain_auth_token` | `- ` | `slg/urls.py` |
| `/muenztyp/` | `views.MuenztypListCreate.as_view(` | `- ` | `slg/urls.py` |
| `/objekt/` | `views.ObjektList.as_view(` | `- ` | `slg/urls.py` |
| `/avbildtyp/` | `views.AvBildtypList.as_view(` | `- ` | `slg/urls.py` |
| `/avbildtyp/<int:pk>/` | `views.AvBildtypDetail.as_view(` | `- ` | `slg/urls.py` |
| `/rvbildtyp/` | `views.RvBildtypList.as_view(` | `- ` | `slg/urls.py` |
| `/rvbildtyp/<int:pk>/` | `views.RvBildtypDetail.as_view(` | `- ` | `slg/urls.py` |
| `/mzstaette/` | `views.MzstaetteList.as_view(` | `- ` | `slg/urls.py` |
| `/mzstaette/<int:pk>/` | `views.MzstaetteDetail.as_view(` | `- ` | `slg/urls.py` |
| `/nominal/` | `views.NominalList.as_view(` | `- ` | `slg/urls.py` |
| `/person/` | `views.PersonList.as_view(` | `- ` | `slg/urls.py` |
| `/nominal/<int:pk>/` | `views.NominalDetail.as_view(` | `- ` | `slg/urls.py` |
| `/herstellungsmerkmale/` | `views.HerstellungsmerkmaleList.as_view(` | `- ` | `slg/urls.py` |
| `/sek_merkmale/` | `views.Sek_MerkmaleList.as_view(` | `- ` | `slg/urls.py` |
| `/muenzstand/` | `views.MuenzstandList.as_view(` | `- ` | `slg/urls.py` |
| `/muenzstand/<int:pk>/` | `views.MuenzstandDetail.as_view(` | `- ` | `slg/urls.py` |
| `/avbeizeichen/` | `views.AvBeizeichenList.as_view(` | `- ` | `slg/urls.py` |
| `/avbeizeichen/<int:pk>/` | `views.AvBeizeichenDetail.as_view(` | `- ` | `slg/urls.py` |
| `/avoffizin/` | `views.AvOffizinList.as_view(` | `- ` | `slg/urls.py` |
| `/avoffizin/<int:pk>/` | `views.AvOffizinDetail.as_view(` | `- ` | `slg/urls.py` |
| `/rvbeizeichen/` | `views.RvBeizeichenList.as_view(` | `- ` | `slg/urls.py` |
| `/rvbeizeichen/<int:pk>/` | `views.RvBeizeichenDetail.as_view(` | `- ` | `slg/urls.py` |
| `/rvoffizin/` | `views.RvOffizinList.as_view(` | `- ` | `slg/urls.py` |
| `/rvoffizin/<int:pk>/` | `views.RvOffizinDetail.as_view(` | `- ` | `slg/urls.py` |
| `/ref/` | `views.RefList.as_view(` | `- ` | `slg/urls.py` |
| `/person_coin_images/` | `views.PersonCoinImagesView.as_view(` | `- ` | `slg/urls.py` |
| `/avschlagwort/` | `views.AvSchlagwortList.as_view(` | `- ` | `slg/urls.py` |
| `/avbildtyp-schlagwort/` | `views.AvBildtypSchlagwortList.as_view(` | `- ` | `slg/urls.py` |
| `/slgteil/<int:slg_id>/` | `views.SlgTeilListAPIView.as_view(` | `- ` | `slg/urls.py` |
| `/api/slgteile/<int:slg_id>/` | `views.SlgTeilListAPIView.as_view(` | `- ` | `slg/urls.py` |
| `/api/adjacent-invnrs/` | `views.get_adjacent_invnrs` | `- ` | `slg/urls.py` |
| `/kontakt/` | `views.kontakt` | `- ` | `slg/urls.py` |
| `/objekt/<int:objekt_id>/aenderung/` | `views.objekt_aenderung` | `- ` | `slg/urls.py` |
| `/tools/graph/` | `views.graph_view` | `slg/graphv0.2.html ` | `slg/urls.py` |
| `/api/area-chart-data/` | `views.area_chart_data` | `- ` | `slg/urls.py` |
| `/api/facet/` | `views.facet_api` | `- ` | `slg/urls.py` |
| `/api/sammlungen/` | `views.sammlungen_api` | `- ` | `slg/urls.py` |
| `/api/collections/` | `views.collections_api` | `- ` | `slg/urls.py` |
| `/api/stats/` | `views.stats_api` | `- ` | `slg/urls.py` |
| `/api/muenzen/<int:pk>/kontext/` | `views.CoinsContextAPI.as_view(` | `- ` | `slg/urls.py` |
| `/api/cycle-coin/` | `views.cycle_coin` | `- ` | `slg/urls.py` |
| `/api/ereignisse/` | `views.ereignisse_api` | `- ` | `slg/urls.py` |
| `/timeline/` | `cache_page(60 * 5` | `- ` | `slg/urls.py` |
| `/catalog/sort-titles/` | `views.catalog_sort_titles` | `slg/catalog_sort_titles.html ` | `slg/urls.py` |
| `/catalog/generate/` | `views.catalog_generate` | `- ` | `slg/urls.py` |
| `/tools/excel-ocre-enrich/` | `views.excel_ocre_enrich` | `slg/excel_ocre_enrich.html ` | `slg/urls.py` |
