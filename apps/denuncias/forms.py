# apps/denuncias/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.core.files.uploadedfile import InMemoryUploadedFile

from .models import (
    Denuncia,
    DenunciaDocumentoImovel,
    DenunciaAnexo,
)


class DenunciaOrigemForm(forms.ModelForm):
    class Meta:
        model = Denuncia
        fields = [
            # origem/denunciante
            "origem_denuncia",
            "denunciante_anonimo",
            "denunciante_fiscal",
            "denunciante_nome",
            "denunciante_email",
            "denunciante_telefone",

            # denunciado
            "denunciado_tipo_pessoa",
            "denunciado_nome_razao",
            "denunciado_cpf_cnpj",
            "denunciado_rg_ie",
            "denunciado_email",
            "denunciado_telefone",

            # --- ENDEREÇO DO DENUNCIADO ---
            "denunciado_res_logradouro",
            "denunciado_res_numero",
            "denunciado_res_complemento",
            "denunciado_res_bairro",
            "denunciado_res_cidade",
            "denunciado_res_uf",
            "denunciado_res_cep",

            # local da ocorrência
            "local_oco_logradouro",
            "local_oco_numero",
            "local_oco_complemento",
            "local_oco_bairro",
            "local_oco_cidade",
            "local_oco_uf",
            "local_oco_cep",
            "local_oco_lat",
            "local_oco_lng",
            "descricao_oco",
        ]

# Retirado o comentário para dar sequência do cadastro de fotos
# --- EDIÇÃO: inclui status/procedencia/ativo ---
class DenunciaEditForm(forms.ModelForm):
    class Meta:
        model = Denuncia
        fields = [
            # pode permitir editar o que fizer sentido + estes:
            "status",
            "procedencia",
            "ativo",
            "descricao_oco",
        ]

# ============================================================
# 2) Inline Formsets (documentos e anexos genéricos)
# ============================================================

class DenunciaDocumentoImovelForm(forms.ModelForm):
    class Meta:
        model = DenunciaDocumentoImovel
        fields = ["tipo", "arquivo", "observacao"]

class DenunciaAnexoForm(forms.ModelForm):
    class Meta:
        model = DenunciaAnexo
        fields = ["tipo", "arquivo", "observacao"]

DocumentoImovelFormSet = inlineformset_factory(
    parent_model=Denuncia,
    model=DenunciaDocumentoImovel,
    form=DenunciaDocumentoImovelForm,
    extra=2,
    can_delete=True,
)

AnexoFormSet = inlineformset_factory(
    parent_model=Denuncia,
    model=DenunciaAnexo,
    form=DenunciaAnexoForm,
    extra=2,
    can_delete=True,
)

# ============================================================
# 3) Fotos múltiplas com pipeline (já usado nas views/templates)
# ============================================================

# ---- Config do pipeline ----
from PIL import Image, ImageOps
import io, hashlib, imghdr, os

TARGET_W = 1000
TARGET_H = 667            # 3:2
TARGET_KB = 103
TOL_KB_MIN = 90
TOL_KB_MAX = 115
JPEG_QUALITY_MIN = 40
JPEG_QUALITY_MAX = 95

ALLOWED_IMAGE_EXTS = {"jpeg", "jpg", "png", "webp", "heic", "heif", "tiff"}

# ---- Widget para múltiplos arquivos ----
class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

# ---- Utilitários ----
def _is_image_file(file_obj) -> bool:
    head = file_obj.read(8192)
    file_obj.seek(0)
    kind = imghdr.what(None, h=head)
    if kind in ALLOWED_IMAGE_EXTS:
        return True
    try:
        Image.open(file_obj).verify()
        file_obj.seek(0)
        return True
    except Exception:
        file_obj.seek(0)
        return False

def _auto_orient(img: Image.Image) -> Image.Image:
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img

def _crop_to_ratio(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    target_ratio = target_w / target_h
    w, h = img.size
    current_ratio = w / h
    if abs(current_ratio - target_ratio) < 1e-3:
        return img
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x1 = (w - new_w) // 2
        box = (x1, 0, x1 + new_w, h)
    else:
        new_h = int(w / target_ratio)
        y1 = (h - new_h) // 2
        box = (0, y1, w, y1 + new_h)
    return img.crop(box)

def _resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    return img.resize((target_w, target_h), Image.LANCZOS)

def _save_jpeg_progressive(img: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()

def _binary_search_quality(img: Image.Image, target_kb: int, tol_min: int, tol_max: int) -> bytes:
    low, high = JPEG_QUALITY_MIN, JPEG_QUALITY_MAX
    best_bytes, best_diff = None, float("inf")
    while low <= high:
        mid = (low + high) // 2
        data = _save_jpeg_progressive(img, mid)
        size_kb = len(data) // 1024
        diff = abs(size_kb - target_kb)
        if diff < best_diff:
            best_diff, best_bytes = diff, data
        if size_kb > tol_max:
            high = mid - 1
        elif size_kb < tol_min:
            low = mid + 1
        else:
            return data
    return best_bytes

def _hash_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _make_inmemory_uploaded_jpg(data: bytes, name_hint: str) -> InMemoryUploadedFile:
    file_io = io.BytesIO(data)
    file_size = file_io.getbuffer().nbytes
    base = os.path.splitext(os.path.basename(name_hint))[0] or "foto"
    new_name = f"{base}.jpg"
    return InMemoryUploadedFile(
        file=file_io,
        field_name="arquivo",
        name=new_name,
        content_type="image/jpeg",
        size=file_size,
        charset=None,
    )

def process_photo_file(file_obj):
    if not _is_image_file(file_obj):
        raise ValidationError("Arquivo não reconhecido como imagem válida.")
    img = Image.open(file_obj)
    img = _auto_orient(img)
    img = _crop_to_ratio(img, TARGET_W, TARGET_H)
    img = _resize(img, TARGET_W, TARGET_H)
    data = _binary_search_quality(img, TARGET_KB, TOL_KB_MIN, TOL_KB_MAX)
    largura, altura = img.size
    file_hash = _hash_sha256(data)
    uploaded = _make_inmemory_uploaded_jpg(data, getattr(file_obj, "name", "foto"))
    return uploaded, largura, altura, file_hash

# ---- Form de múltiplas fotos ----
class DenunciaFotosForm(forms.Form):
    fotos = forms.FileField(
        widget=MultiFileInput(
            attrs={
                "multiple": True,
                "accept": "image/*",
                "capture": "environment",
            }
        ),
        required=False,
        help_text="Envie até 4 fotos (somando as já existentes).",
    )
    observacao = forms.CharField(
        required=False,
        max_length=140,
        widget=forms.TextInput(attrs={"placeholder": "Observação (opcional)"}),
    )

    def __init__(self, *args, denuncia: Denuncia | None = None, **kwargs):
        self.denuncia = denuncia
        super().__init__(*args, **kwargs)

    def clean_fotos(self):
        files = self.files.getlist("fotos")
        if not files:
            return files
        for f in files:
            if not _is_image_file(f):
                raise ValidationError("Um dos arquivos não é uma imagem válida.")
        existentes = self.denuncia.anexos.filter(tipo="FOTO").count() if self.denuncia else 0
        novas = len(files)
        if existentes + novas > 4:
            restante = max(0, 4 - existentes)
            raise ValidationError(
                f"Limite de 4 fotos por denúncia. Você já tem {existentes}. "
                f"Envie no máximo {restante} agora."
            )
        return files

    def save(self):
        if not self.denuncia:
            raise ValidationError("A denúncia deve ser informada para salvar as fotos.")
        created = []
        files = self.cleaned_data.get("fotos", [])
        obs = (self.cleaned_data.get("observacao") or "").strip()
        for f in files:
            processed_file, w, h, hsh = process_photo_file(f)
            anexo = DenunciaAnexo(
                denuncia=self.denuncia,
                tipo="FOTO",
                arquivo=processed_file,
                observacao=obs[:140] if obs else "",
                largura_px=w,
                altura_px=h,
                hash_sha256=hsh,
                otimizada=True,
            )
            anexo.save()
            created.append(anexo)
        return created
