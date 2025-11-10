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
    path("<int:pk>/vincular-pessoa/", views.denuncia_vincular_pessoa, name="vincular_pessoa"),
    path("<int:pk>/vincular-imovel/", views.denuncia_vincular_imovel, name="vincular_imovel"),
    path("apontamentos/novo/<int:den_pk>/", views.apontamento_novo, name="apontamento_novo"),
    path("imprimir/<int:pk>/", views.denuncia_imprimir, name="imprimir"),
    path("<int:pk>/editar/", views.denuncia_edit_basico, name="editar_basico"),
    path("<int:pk>/editar-completo/", views.denuncia_editar_completo, name="editar_completo"),
    path("<int:pk>/set-procedencia/", views.denuncia_set_procedencia, name="set_procedencia"),
    path("<int:pk>/", views.denuncia_detail, name="detalhe"),
]
