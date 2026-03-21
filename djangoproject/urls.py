"""djangoproject URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

Add django_select to your urlconf if you use any ModelWidgets:

url(r'^select2/', include('django_select2.urls')),
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.cache import cache_page
from rest_framework import routers, serializers, viewsets

from slg.api_views import ExportObjLSNO

from slg.views import about, objekt_detail_partial, export_xlsx, get_konkordanzen, PraegeherrTimelineView, RvSchlagwortTimelineView, NominalModalView, PersonModalView, SammlungView, ObjektView, objekt_list_view, MzstaettenRView, jsonresp, rdfliboutput, MzUpdate, ObjCreateView, ObjUpdateView, TypView, AvSchlagwortView, RvSchlagwortView, ObjektDetail, objekt_list_view_mtoa


urlpatterns = [
    path('about/', about, name='about'),
    path('admin/', admin.site.urls),
    #path('posts/', include('posts.urls')),
    #path('slg/', include('slg.urls')),
    path('slg/<int:id>/', SammlungView, name='Sammlung'),
    path('objekt/<int:id>/', ObjektView, name='Objekt'),
    path('typ/<int:id>/', TypView, name='Typ'),
    path('av_schlagwort/<int:id>/', AvSchlagwortView, name='AvSchlagwort'),
    path('rv_schlagwort/<int:id>/', RvSchlagwortView, name='RvSchlagwort'),
    path('rv_schlagwort/<int:id>/timeline', RvSchlagwortTimelineView, name='RvSchlagwortTimeline'),
    
    path('person/<int:id>/timeline', PraegeherrTimelineView, name='PraegeherrTimeline'),
    path('person/<int:id>/modal/', PersonModalView, name='PersonModal'),
    path('nominal/<int:id>/modal/', NominalModalView, name='NominalModal'),
    path('id/<int:id>/update/', MzUpdate, name='Objekt_Update'),
    path('id/<int:pk>/edit/', ObjUpdateView.as_view(), name='update_object'),
    path('create/', ObjCreateView.as_view(), name='create_object'),
    # path('id/<int:id>/update/', MzUpdate.as_view(), name='Objekt'),
    path('id/<int:id>.ttl', rdfliboutput, name='ObjTTl'),
    #path('slg/<int:id>.json', jsonresp, name='Objekt'),
    path('browse/', cache_page(60 * 5)(objekt_list_view_mtoa), name='Objektliste'),
    path('browse_legacy/', cache_page(60 * 5)(objekt_list_view), name='Objektliste_legacy'),
    # path('slg/objekte/', include('django_select2.urls'), objekt_list_view, name='Objektliste'),
    #path('select2/',include('django_select2.urls')),
    #path('api-auth/', include('rest_framework.urls')),
    path('', include('slg.urls'), name='index'),
    # WICHTIG: Spezifische API-Routen müssen VOR dem allgemeinen 'api/' include stehen!
    # Die Reihenfolge ist kritisch: Django prüft URLs von oben nach unten.
    # Wenn 'api/' include zuerst kommt, wird 'api/objekt/<invnr>/' nie erreicht.
    path('api/objekt/<str:invnr>/', ObjektDetail.as_view(), name='api-objekt-detail'),
    path('api/', include('slg.urls')),  # Allgemeine API-Routen (muss NACH spezifischen Routen stehen!)
    path('select2/', include('django_select2.urls')),
    path('adminactions/', include('adminactions.urls')),
    #path('api/postings/', include('slg.api.urls', 'slg', namespace='api-postings'))
    path('ajax/get-konkordanzen/', get_konkordanzen, name='get-konkordanzen'),
    path('export-obj-lsno/', ExportObjLSNO.as_view(), name='export-obj-lsno'),
    path('export_xlsx/', export_xlsx, name='export_xlsx'),
    path('objekt_detail_partial/', objekt_detail_partial, name='objekt_detail_partial'),
] 





if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

# Nur Media-URLs hinzufügen, wenn MEDIA_URL gesetzt ist (nicht leer)
if settings.MEDIA_URL:
    urlpatterns = urlpatterns + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)