# apps/denuncias/urls.py
from django.urls import path
from . import views
app_name = 'denuncias'

urlpatterns = [
    #path("", views.listar_denuncias, name="denuncias_listar"),
    #path("nova/", views.cadastrar_denuncia, name="denuncias_cadastrar"),
    #path("<int:pk>/", views.detalhe_denuncia, name="denuncias_detalhe"),
    #path("<int:pk>/editar/", views.editar_denuncia, name="denuncias_editar"),
    path("nova-step1/", views.denuncia_nova_step1, name="nova_step1"),
]
