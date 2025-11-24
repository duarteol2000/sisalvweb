from django.contrib import admin
from django.urls import path, include
from apps.usuarios.views import login_view, logout_view, home_view
from django.conf import settings
from sisalvweb import core_views
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("", home_view, name="home"),

    # ✅ denuncias com namespace
    path("denuncias/", include(("apps.denuncias.urls", "denuncias"), namespace="denuncias")),
    path("", include(("apps.usuarios.urls", "usuarios"), namespace="usuarios")),

    path("notificacoes/", include("apps.notificacoes.urls", namespace="notificacoes")),
    path("autoinfracao/", include(("apps.autoinfracao.urls", "autoinfracao"), namespace="autoinfracao")),
    # Mapa
    path("mapa/", core_views.mapa_view, name="core_mapa"),
    path("api/mapa/processos/", core_views.api_mapa_processos, name="core_api_mapa_processos"),
    path("api/mapa/heat/", core_views.api_mapa_heat, name="core_api_mapa_heat"),
    # Relatórios
    path("relatorios/operacional/", core_views.relatorio_operacional, name="relatorio_operacional"),
    # Relatórios — Analytics
    path("relatorios/risco/", core_views.relatorio_risco, name="relatorio_risco"),
    path("relatorios/fiscais/", core_views.relatorio_fiscais, name="relatorio_fiscais"),
    path("relatorios/fiscais/quantitativo/", core_views.relatorio_fiscais_quantitativo, name="relatorio_fiscais_quantitativo"),
    path("relatorios/fiscais/bairros/", core_views.relatorio_fiscais_bairros, name="relatorio_fiscais_bairros"),
    # Relatórios — Pessoa 360
    path("relatorios/pessoa/", core_views.relatorio_pessoa_busca, name="relatorio_pessoa_busca"),
    path("relatorios/pessoa/<int:pessoa_id>/", core_views.relatorio_pessoa, name="relatorio_pessoa"),
    path("relatorios/pessoa/<int:pessoa_id>/csv/", core_views.relatorio_pessoa_csv, name="relatorio_pessoa_csv"),
    path("relatorios/pessoa/<int:pessoa_id>/imprimir/", core_views.relatorio_pessoa_imprimir, name="relatorio_pessoa_imprimir"),
    
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
