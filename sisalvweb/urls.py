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
    path('denuncias/', include('apps.denuncias.urls', namespace='denuncias')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
