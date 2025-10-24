from django import forms
from django.db.models import Q
from apps.autoinfracao.models import AutoInfracao, InfracaoTipo, Enquadramento, AutoInfracaoMultaItem, AutoInfracaoAnexo
from apps.autoinfracao.models import Embargo, Interdicao, EmbargoAnexo, InterdicaoAnexo
from apps.usuarios.models import Usuario
from django.db import models


class HTML5DateInput(forms.DateInput):
    input_type = "date"
    def __init__(self, *args, **kwargs):
        # Garante exibição do valor no input date (YYYY-MM-DD)
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class AutoInfracaoCreateForm(forms.ModelForm):
    tipos = forms.ModelMultipleChoiceField(
        queryset=InfracaoTipo.objects.none(), required=False, label="Tipos de Infração"
    )
    fiscais = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(), required=False, label="Fiscais"
    )

    class Meta:
        model = AutoInfracao
        fields = [
            # notificado
            "pessoa_tipo", "nome_razao", "cpf_cnpj", "rg", "telefone", "email",
            # endereço
            "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
            # geolocalização
            "latitude", "longitude",
            # construtivo
            "area_m2", "testada_m", "pe_direito_m", "duplex", "qtd_comodos", "compartimentacao", "divisorias", "mezanino", "area_mezanino_m2",
            # dados
            "descricao",
            # prazos/valores
            "prazo_regularizacao_data", "valor_infracao", "valor_multa_homologado",
        ]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "area_m2": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 120.50"}),
            "testada_m": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 7.50"}),
            "pe_direito_m": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 2.80"}),
            "area_mezanino_m2": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 30.00"}),
            "prazo_regularizacao_data": HTML5DateInput(),
            "valor_infracao": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
            "valor_multa_homologado": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        prefeitura_id = kwargs.pop("prefeitura_id", None)
        super().__init__(*args, **kwargs)
        # Aceitar ISO do browser e formato BR
        if "prazo_regularizacao_data" in self.fields:
            self.fields["prazo_regularizacao_data"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        if prefeitura_id:
            local_qs = InfracaoTipo.objects.filter(prefeitura_id=prefeitura_id, ativo=True)
            global_qs = InfracaoTipo.objects.filter(prefeitura__isnull=True, ativo=True)
            if local_qs.exists():
                base_qs = local_qs
            else:
                base_qs = global_qs
            # Garante que valores já vinculados permaneçam visíveis
            if getattr(self.instance, 'pk', None):
                selecionados = list(self.instance.tipos.all().values_list('pk', flat=True))
                if selecionados:
                    base_qs = (base_qs | InfracaoTipo.objects.filter(pk__in=selecionados))
            self.fields["tipos"].queryset = base_qs.order_by("nome").distinct()
            # Volta para SelectMultiple (estável em todos os navegadores)
            self.fields["tipos"].widget = forms.SelectMultiple(attrs={"size": "10"})
            self.fields["fiscais"].queryset = Usuario.objects.filter(
                prefeitura_id=prefeitura_id
            ).order_by("first_name", "last_name", "email")

    def clean(self):
        data = super().clean()
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")
        return data


class AutoInfracaoMultaItemForm(forms.ModelForm):
    class Meta:
        model = AutoInfracaoMultaItem
        fields = ["enquadramento", "valor_unitario", "valor_homologado", "descricao"]

    def __init__(self, *args, **kwargs):
        prefeitura_id = kwargs.pop("prefeitura_id", None)
        super().__init__(*args, **kwargs)
        if prefeitura_id:
            self.fields["enquadramento"].queryset = Enquadramento.objects.filter(
                prefeitura_id=prefeitura_id, ativo=True
            ).order_by("descricao")
        # Rótulos amigáveis
        self.fields["valor_unitario"].label = "Valor da Multa"
        self.fields["valor_homologado"].label = "Valor Homologado"

    def clean(self):
        data = super().clean()
        vm = data.get("valor_unitario")
        vh = data.get("valor_homologado")
        if vh in (None, "") and vm not in (None, ""):
            data["valor_homologado"] = vm
        return data


class AutoInfracaoEditForm(AutoInfracaoCreateForm):
    class Meta(AutoInfracaoCreateForm.Meta):
        fields = AutoInfracaoCreateForm.Meta.fields + ["status"]

    def clean(self):
        data = super().clean()
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")
        return data

class InfracaoTipoForm(forms.ModelForm):
    class Meta:
        model = InfracaoTipo
        fields = ["codigo", "nome", "descricao", "ativo"]


class EnquadramentoForm(forms.ModelForm):
    class Meta:
        model = Enquadramento
        fields = ["codigo", "artigo", "descricao", "valor_base", "ativo"]


# ====== Embargo / Interdição ======

class EmbargoEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "prazo_regularizacao_data" in self.fields:
            self.fields["prazo_regularizacao_data"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
    class Meta:
        model = Embargo
        fields = [
            "status",
            "licenca_tipo",
            "prazo_regularizacao_data",
            "exigencias_texto",
            "afixado_no_local_em",
            "entregue_ao_responsavel_em",
        ]
        widgets = {
            "prazo_regularizacao_data": HTML5DateInput(),
            "exigencias_texto": forms.Textarea(attrs={"rows": 4}),
        }


class InterdicaoEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "prazo_regularizacao_data" in self.fields:
            self.fields["prazo_regularizacao_data"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
    class Meta:
        model = Interdicao
        fields = [
            "status",
            "motivo_tipo",
            "prazo_regularizacao_data",
            "condicoes_texto",
            "afixado_no_local_em",
            "entregue_ao_responsavel_em",
        ]
        widgets = {
            "prazo_regularizacao_data": HTML5DateInput(),
            "condicoes_texto": forms.Textarea(attrs={"rows": 4}),
        }


class EmbargoAnexoForm(forms.ModelForm):
    class Meta:
        model = EmbargoAnexo
        fields = ["tipo", "arquivo", "observacao"]


class InterdicaoAnexoForm(forms.ModelForm):
    class Meta:
        model = InterdicaoAnexo
        fields = ["tipo", "arquivo", "observacao"]


class AutoInfracaoAnexoForm(forms.ModelForm):
    class Meta:
        model = AutoInfracaoAnexo
        fields = ["tipo", "arquivo", "observacao"]
