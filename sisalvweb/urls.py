from django.contrib import admin
from django.urls import path, include
from apps.usuarios.views import login_view, logout_view, home_view
from django.conf import settings
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
    
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
