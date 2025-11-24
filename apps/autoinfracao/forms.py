from django import forms
from django.db.models import Q
from apps.autoinfracao.models import AutoInfracao, InfracaoTipo, Enquadramento, AutoInfracaoMultaItem, AutoInfracaoAnexo
from apps.autoinfracao.models import Embargo, Interdicao, EmbargoAnexo, InterdicaoAnexo
from apps.usuarios.models import Usuario
from django.db import models
from utils.num import to_decimal


class HTML5DateInput(forms.DateInput):
    input_type = "date"
    def __init__(self, *args, **kwargs):
        # Garante exibição do valor no input date (YYYY-MM-DD)
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class HTML5DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"
    def __init__(self, *args, **kwargs):
        # Formato padrão do input datetime-local: YYYY-MM-DDTHH:MM
        kwargs.setdefault("format", "%Y-%m-%dT%H:%M")
        super().__init__(*args, **kwargs)


class AutoInfracaoCreateForm(forms.ModelForm):
    # Evita validação nativa de FloatField com vírgula; converteremos no clean
    latitude = forms.CharField(required=False)
    longitude = forms.CharField(required=False)
    # Evita validação nativa de DecimalField com vírgula; tratamos no clean
    valor_infracao = forms.CharField(required=False)
    valor_multa_homologado = forms.CharField(required=False)
    ocorrido_em = forms.CharField(required=False)
    # Evita validação nativa para campos decimais de construção; tratamos no clean
    area_m2 = forms.CharField(required=False)
    testada_m = forms.CharField(required=False)
    pe_direito_m = forms.CharField(required=False)
    area_mezanino_m2 = forms.CharField(required=False)
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
            "prazo_regularizacao_data", "ocorrido_em", "valor_infracao", "valor_multa_homologado",
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
            "ocorrido_em": forms.DateTimeInput(attrs={"type": "datetime-local"}),
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
        # E-mail opcional e sem atributo required no HTML
        if 'email' in self.fields:
            self.fields['email'].required = False
            try:
                if 'required' in (self.fields['email'].widget.attrs or {}):
                    del self.fields['email'].widget.attrs['required']
            except Exception:
                pass
        # Padroniza widget/label e valor inicial do ocorrido_em para datetime-local
        if "ocorrido_em" in self.fields:
            try:
                self.fields["ocorrido_em"].label = "Data/Hora do Ocorrido"
                self.fields["ocorrido_em"].widget = forms.DateTimeInput(attrs={"type": "datetime-local"})
                occ = self.initial.get("ocorrido_em") or getattr(self.instance, "ocorrido_em", None)
                if occ:
                    from datetime import datetime
                    try:
                        self.initial["ocorrido_em"] = occ.strftime("%Y-%m-%dT%H:%M")
                    except Exception:
                        pass
            except Exception:
                pass
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
                prefeitura_id=prefeitura_id,
                is_active=True,
                tipo__iexact='FISCAL',
            ).order_by("first_name", "last_name", "email")
            # Checkboxes mais visíveis
            self.fields["fiscais"].widget = forms.CheckboxSelectMultiple()
            try:
                self.fields['fiscais'].label_from_instance = lambda u: (
                    (u.get_full_name() or u.email) + (f" ({u.matricula})" if getattr(u, 'matricula', None) else '')
                )
            except Exception:
                pass
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
        # Data/hora do ocorrido: aceita 'YYYY-MM-DDTHH:MM' e 'dd/mm/YYYY HH:MM'
        raw_occ = self.data.get("ocorrido_em") if hasattr(self, 'data') else None
        if raw_occ:
            from datetime import datetime
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
                try:
                    data["ocorrido_em"] = datetime.strptime(raw_occ.strip(), fmt)
                    break
                except Exception:
                    continue
            else:
                self.add_error("ocorrido_em", "Data/hora inválida. Use o seletor ou 'dd/mm/aaaa hh:mm'.")
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
        # Normaliza campos decimais (aceita vírgula) usando utils.num
        # Quantiza para 2 casas os monetários/áreas
        from decimal import Decimal
        two = Decimal("0.01")
        def _apply_decimal(field, quant=False):
            v = self.data.get(field, data.get(field))
            d = to_decimal(v, quantize_exp=two if quant else None)
            if v in (None, ""):
                data[field] = None
            elif d is None:
                self.add_error(field, "Valor inválido. Use ponto ou vírgula como decimal.")
            else:
                data[field] = d
        # Áreas/valores
        for f in ("area_m2", "testada_m", "pe_direito_m", "area_mezanino_m2"):
            _apply_decimal(f, quant=True)
        for f in ("valor_infracao", "valor_multa_homologado"):
            _apply_decimal(f, quant=True)
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
    # Também tratar pagamentos como texto para aceitar vírgula na entrada
    valor_pago = forms.CharField(required=False)
    class Meta(AutoInfracaoCreateForm.Meta):
        fields = AutoInfracaoCreateForm.Meta.fields + [
            "status",
            # pagamento
            "pago", "valor_pago", "pago_em", "forma_pagamento", "guia_numero", "observacao_pagamento",
        ]
        widgets = dict(AutoInfracaoCreateForm.Meta.widgets, **{
            "pago_em": HTML5DateInput(),
            "valor_pago": forms.TextInput(attrs={"class": "js-decimal-2", "inputmode": "decimal", "placeholder": "ex.: 100,00"}),
        })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'email' in self.fields:
            self.fields['email'].required = False
            try:
                if 'required' in (self.fields['email'].widget.attrs or {}):
                    del self.fields['email'].widget.attrs['required']
            except Exception:
                pass
        # Já herdou a padronização de ocorrido_em no __init__ da classe base
        if "pago_em" in self.fields:
            self.fields["pago_em"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]

    def clean(self):
        data = super().clean()
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")
        # Normaliza valor_pago com quantização
        from decimal import Decimal
        two = Decimal("0.01")
        raw = self.data.get("valor_pago") if hasattr(self, 'data') else None
        if (raw in (None, "")) and (data.get("valor_pago") in (None, "")):
            data["valor_pago"] = None
        else:
            d = to_decimal(raw if raw is not None else data.get("valor_pago"), quantize_exp=two)
            if d is None:
                self.add_error("valor_pago", "Valor inválido. Use ponto ou vírgula como decimal.")
            else:
                data["valor_pago"] = d
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
        # Aceitar datetime-local nos campos de afixação/entrega
        for fld in ("afixado_no_local_em", "entregue_ao_responsavel_em"):
            if fld in self.fields:
                self.fields[fld].input_formats = [
                    "%Y-%m-%dT%H:%M",  # HTML5 datetime-local
                    "%Y-%m-%d %H:%M",
                    "%d/%m/%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S",
                ]
    class Meta:
        model = Embargo
        fields = [
            "status",
            "licenca_tipo",
            "exigencias_texto",
            "afixado_no_local_em",
            "entregue_ao_responsavel_em",
        ]
        widgets = {
            "exigencias_texto": forms.Textarea(attrs={"rows": 4}),
            "afixado_no_local_em": HTML5DateTimeLocalInput(),
            "entregue_ao_responsavel_em": HTML5DateTimeLocalInput(),
        }


class InterdicaoEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "prazo_regularizacao_data" in self.fields:
            self.fields["prazo_regularizacao_data"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        for fld in ("afixado_no_local_em", "entregue_ao_responsavel_em"):
            if fld in self.fields:
                self.fields[fld].input_formats = [
                    "%Y-%m-%dT%H:%M",
                    "%Y-%m-%d %H:%M",
                    "%d/%m/%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S",
                ]
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
            "afixado_no_local_em": HTML5DateTimeLocalInput(),
            "entregue_ao_responsavel_em": HTML5DateTimeLocalInput(),
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


class AutoInfracaoDefesaForm(forms.ModelForm):
    class Meta:
        model = AutoInfracaoAnexo
        fields = ["arquivo", "observacao"]
