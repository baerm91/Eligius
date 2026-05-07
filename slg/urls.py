from django.urls import path, include
from django.views.decorators.cache import cache_page
from rest_framework import routers
from . import views
from . import api_views
#from .views import MzstaettenRView

router = routers.DefaultRouter()
router.register('mints/', views.MzstaettenRView)
urlpatterns = [
    path('', cache_page(60 * 5)(views.index), name="index_slg"),
    path('neuerschliessungen/', cache_page(60 * 5)(views.neuerschliessungen), name='neuerschliessungen'),
    path('about/', cache_page(60 * 30)(views.about), name="about"),
    #path('', include(router.urls)) 
    #path('<id>/', views.details, name="details_slg")
    path('api-token-auth/', api_views.obtain_auth_token, name='api_token_auth'),
    path('muenztyp/', views.MuenztypListCreate.as_view()),
    path('muenztyp/konkordanz/', views.muenztyp_konkordanz_create),
    path('muenztyp/<int:type_id>/konkordanz/', views.muenztyp_konkordanz_create),
    path('muenztyp/<int:type_id>/duplicate/', views.MuenztypDuplicateView.as_view()),
    path('muenztyp_from_concordia/', views.ConcordiaMuenztypCreateView.as_view()),
    path('muenztyp_filter/', views.MuenztypFilterView.as_view()),
    path('konkordanzen_bulk/', views.konkordanzen_bulk),
    path('export_coins/', views.export_coins_api, name='export_coins_api'),
    path('export_coin_states/', views.export_coin_states_api, name='export_coin_states_api'),
    path('objekt/', views.ObjektList.as_view()),
    path('objekt/<str:invnr>/personen/', views.ObjektPersonenView.as_view(), name='api-objekt-personen'),
    # API-Route 'objekt/<str:invnr>/' entfernt, da sie mit der Detailseiten-Route 'objekt/<int:id>/' kollidiert
    # Die API-Route ist weiterhin unter /api/objekt/<str:invnr>/ verfügbar
    path('avbildtyp/', views.AvBildtypList.as_view()),
    path('avbildtyp/<int:pk>/', views.AvBildtypDetail.as_view()),
    path('rvbildtyp/', views.RvBildtypList.as_view()),
    path('rvbildtyp/<int:pk>/', views.RvBildtypDetail.as_view()),
    path('mzstaette/', views.MzstaetteList.as_view()),
    path('mzstaette/<int:pk>/', views.MzstaetteDetail.as_view()),
    path('nominal/', views.NominalList.as_view()),
    path('person/', views.PersonList.as_view()),
    path('nominal/<int:pk>/', views.NominalDetail.as_view()),
    path('herstellungsmerkmale/', views.HerstellungsmerkmaleList.as_view()),
    path('sek_merkmale/', views.Sek_MerkmaleList.as_view()),
    path('muenzstand/', views.MuenzstandList.as_view()),
    path('muenzstand/<int:pk>/', views.MuenzstandDetail.as_view()),
    path('avbeizeichen/', views.AvBeizeichenList.as_view()),
    path('avbeizeichen/<int:pk>/', views.AvBeizeichenDetail.as_view()),
    path('avoffizin/', views.AvOffizinList.as_view()),
    path('avoffizin/<int:pk>/', views.AvOffizinDetail.as_view()),
    path('rvbeizeichen/', views.RvBeizeichenList.as_view()),
    path('rvbeizeichen/<int:pk>/', views.RvBeizeichenDetail.as_view()),
    path('rvoffizin/', views.RvOffizinList.as_view()),
    path('rvoffizin/<int:pk>/', views.RvOffizinDetail.as_view()),
    path('workflow/', views.WorkflowList.as_view()),
    path('workflow/<int:pk>/', views.WorkflowDetail.as_view()),
    path('ref/', views.RefList.as_view()),
    path('person_coin_images/', views.PersonCoinImagesView.as_view(), name='person-coin-images'),
    path('avschlagwort/', views.AvSchlagwortList.as_view(), name='avschlagwort-list'),
    path('avbildtyp-schlagwort/', views.AvBildtypSchlagwortList.as_view(), name='avbildtyp-schlagwort-list'),
    path('slgteil/<int:slg_id>/', views.SlgTeilListAPIView.as_view(), name='slgteil-list'),
    path('api/slgteile/<int:slg_id>/', views.SlgTeilListAPIView.as_view(), name='slgteil-list'),
    path('api/adjacent-invnrs/', views.get_adjacent_invnrs, name='adjacent_invnrs'),
    path('kontakt/', views.kontakt, name='kontakt'),
    path('objekt/<int:objekt_id>/aenderung/', views.objekt_aenderung, name='objekt_aenderung'),
    path('tools/graph/', views.graph_view, name='graph_view'),
    path('api/area-chart-data/', views.area_chart_data, name='area_chart_data'),
    path('api/facet/', views.facet_api, name='facet_api'),
    path('api/sammlungen/', views.sammlungen_api, name='sammlungen_api'),
    path('api/collections/', views.collections_api, name='collections_api'),
    path('api/stats/', views.stats_api, name='stats_api'),
    # path('api/context-coins/', views.context_coins, name='context_coins'),
    path('api/muenzen/<int:pk>/kontext/', views.CoinsContextAPI.as_view(), name='coin-context'),
    path('api/cycle-coin/', views.cycle_coin, name='cycle_coin'),
    # Neue API-Route für die Zeitleiste
    path('api/ereignisse/', views.ereignisse_api, name='ereignisse_api'),
    # Route für die Timeline-Ansicht
    path('timeline/', cache_page(60 * 5)(views.timeline_view), name='timeline_view'),
    # Katalog-URLs
    path('catalog/sort-titles/', views.catalog_sort_titles, name='catalog_sort_titles'),
    path('catalog/generate/', views.catalog_generate, name='catalog_generate'),
    
    # Excel Enrichment
    path('tools/excel-ocre-enrich/', views.excel_ocre_enrich, name='excel_ocre_enrich'),
]
