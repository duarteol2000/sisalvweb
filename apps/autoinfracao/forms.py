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
    # Evita validação nativa de FloatField com vírgula; converteremos no clean
    latitude = forms.CharField(required=False)
    longitude = forms.CharField(required=False)
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
            # Máscaras decimais e inteiros
            "latitude": forms.TextInput(attrs={"class": "js-decimal-6", "inputmode": "decimal", "placeholder": "Ex.: -3,876543"}),
            "longitude": forms.TextInput(attrs={"class": "js-decimal-6", "inputmode": "decimal", "placeholder": "Ex.: -38,654321"}),
            "area_m2": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 120,50"}),
            "testada_m": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 7,50"}),
            "pe_direito_m": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 2,80"}),
            "area_mezanino_m2": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 30,00"}),
            "qtd_comodos": forms.TextInput(attrs={"class": "js-int", "inputmode": "numeric", "placeholder": "ex.: 4"}),
            "prazo_regularizacao_data": HTML5DateInput(),
            "valor_infracao": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 100,00"}),
            "valor_multa_homologado": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 100,00"}),
            # documentos/contatos
            "cpf_cnpj": forms.TextInput(attrs={"class": "js-doc", "inputmode": "numeric", "maxlength": 18}),
            "telefone": forms.TextInput(attrs={"class": "js-phone", "inputmode": "tel"}),
            "cep": forms.TextInput(attrs={"class": "js-cep", "inputmode": "numeric", "maxlength": 9}),
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
        # Força lat/lng com 6 casas na renderização
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        for fld in ("latitude", "longitude"):
            val = self.initial.get(fld) or getattr(self.instance, fld, None)
            if val not in (None, ""):
                try:
                    q = Decimal(str(val)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    self.initial[fld] = f"{q:.6f}"
                except (InvalidOperation, ValueError):
                    pass

    def clean(self):
        data = super().clean()
        # Normaliza lat/lng (vírgula → ponto) e valida faixa
        def _norm(v):
            if v in (None, ""): return v
            if isinstance(v, (int, float)): return v
            s = str(v).strip().replace(" ", ""); s = s.replace(",", "."); return s
        lat = _norm(self.data.get("latitude", data.get("latitude")))
        lng = _norm(self.data.get("longitude", data.get("longitude")))
        try:
            if lat not in (None, ""):
                latf = float(lat)
                if not (-90.0 <= latf <= 90.0):
                    self.add_error("latitude", "Latitude fora do intervalo válido (-90 a 90).")
                else: data["latitude"] = latf
            if lng not in (None, ""):
                lngf = float(lng)
                if not (-180.0 <= lngf <= 180.0):
                    self.add_error("longitude", "Longitude fora do intervalo válido (-180 a 180).")
                else: data["longitude"] = lngf
        except ValueError:
            if lat:
                self.add_error("latitude", "Valor inválido. Use ponto ou vírgula como decimal.")
            if lng:
                self.add_error("longitude", "Valor inválido. Use ponto ou vírgula como decimal.")
        # Normaliza campos decimais (aceita vírgula)
        from decimal import Decimal, InvalidOperation
        def _norm_dec_field(field):
            v = self.data.get(field, data.get(field))
            if v in (None, ""): return
            if isinstance(v, (int, float)):
                data[field] = v
                return
            s = str(v).strip().replace(" ", "").replace(".", "").replace(",", ".")
            try:
                data[field] = Decimal(s)
            except InvalidOperation:
                self.add_error(field, "Valor inválido. Use ponto ou vírgula como decimal.")
        for f in ("area_m2", "testada_m", "pe_direito_m", "area_mezanino_m2", "valor_infracao", "valor_multa_homologado"):
            _norm_dec_field(f)
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
    latitude = forms.CharField(required=False)
    longitude = forms.CharField(required=False)
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
