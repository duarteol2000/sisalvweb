from django.urls import path
from . import views

app_name = "autoinfracao"

urlpatterns = [
    path("listar/", views.listar, name="listar"),
    path("cadastrar/", views.cadastrar, name="cadastrar"),
    path("editar/<int:pk>/", views.editar, name="editar"),
    path("detalhe/<int:pk>/", views.detalhe, name="detalhe"),
    path("confirmar-vinculos/<int:pk>/", views.confirmar_vinculos, name="confirmar_vinculos"),
    path("<int:pk>/vincular-pessoa/", views.vincular_pessoa, name="vincular_pessoa"),
    path("<int:pk>/vincular-imovel/", views.vincular_imovel, name="vincular_imovel"),
    path("imprimir/<int:pk>/", views.imprimir, name="imprimir"),
    # Medidas a partir do AIF
    path("<int:aif_pk>/gerar-embargo/", views.gerar_embargo, name="gerar_embargo"),
    path("<int:aif_pk>/gerar-interdicao/", views.gerar_interdicao, name="gerar_interdicao"),
    path("embargos/<int:pk>/", views.embargo_detalhe, name="embargo_detalhe"),
    path("embargos/<int:pk>/editar/", views.embargo_editar, name="embargo_editar"),
    path("interdicoes/<int:pk>/", views.interdicao_detalhe, name="interdicao_detalhe"),
    path("interdicoes/<int:pk>/editar/", views.interdicao_editar, name="interdicao_editar"),
    # Geração a partir de Notificação
    path("from-notificacao/<int:notif_pk>/", views.gerar_de_notificacao, name="from_notificacao"),
    # Geração a partir de Denúncia
    path("from-denuncia/<int:den_pk>/", views.gerar_de_denuncia, name="from_denuncia"),
    # Listagem de Embargos/Interdições
    path("medidas/", views.medidas_listar, name="medidas_listar"),
    # Catálogos por prefeitura
    path("tipos/", views.tipos_listar, name="tipos_listar"),
    path("tipos/novo/", views.tipos_novo, name="tipos_novo"),
    path("tipos/<int:pk>/editar/", views.tipos_editar, name="tipos_editar"),
    path("enquadramentos/", views.enq_listar, name="enq_listar"),
    path("enquadramentos/novo/", views.enq_novo, name="enq_novo"),
    path("enquadramentos/<int:pk>/editar/", views.enq_editar, name="enq_editar"),
]
