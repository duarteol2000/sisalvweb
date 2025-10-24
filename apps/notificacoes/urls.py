from django.urls import path
from . import views

app_name = "notificacoes"

urlpatterns = [
    path("listar/", views.listar, name="listar"),
    path("nova/", views.criar, name="nova"),
    path("editar/<int:pk>/", views.editar, name="editar"),
    path("detalhe/<int:pk>/", views.detalhe, name="detalhe"),
    path("imprimir/<int:pk>/", views.imprimir, name="imprimir"),
    # gerar a partir de Denúncia
    path("from-denuncia/<int:den_pk>/", views.gerar_de_denuncia, name="from_denuncia"),
]
