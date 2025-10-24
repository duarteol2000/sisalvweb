# apps/denuncias/urls.py
from django.urls import path
from . import views
app_name = 'denuncias'

urlpatterns = [
    # Rota de testes
    path("nova-step1/", views.denuncia_nova_step1, name="nova_step1"),
    # ✅ alias oficial para o menu/botões (aponta para a MESMA view)
    path("cadastrar/", views.denuncia_nova_step1, name="cadastrar_denuncia"),
    path("listar/", views.denuncia_list, name="listar"),
    path("<int:pk>/editar/", views.denuncia_edit_basico, name="editar_basico"),
    path("<int:pk>/", views.denuncia_detail, name="detalhe"),
]
