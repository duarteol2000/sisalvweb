# apps/denuncias/management/commands/purge_fiscalizacao.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
import os
import shutil


class Command(BaseCommand):
    help = (
        "Remove de forma segura todos os registros de Fiscalização: Denúncias, Notificações e Autos de Infração, "
        "incluindo anexos (imagens/PDFs). Por padrão é DRY-RUN. Use --yes para executar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            dest="confirm",
            help="Executa a exclusão (sem esta flag é apenas DRY-RUN).",
        )
        parser.add_argument(
            "--prefeitura",
            type=int,
            default=None,
            help="Opcional: limita a exclusão à prefeitura informada (id).",
        )

    def _del_file(self, ffield):
        try:
            if ffield and getattr(ffield, "name", None):
                storage = getattr(ffield, "storage", None)
                name = ffield.name
                if storage and storage.exists(name):
                    storage.delete(name)
        except Exception:
            # não interrompe o fluxo
            pass

    def _count_qs(self, qs):
        try:
            return qs.count()
        except Exception:
            return 0

    def handle(self, *args, **opts):
        confirm = bool(opts.get("confirm"))
        pref_id = opts.get("prefeitura")
        filters = {}
        if pref_id:
            filters["prefeitura_id"] = pref_id

        # Imports locais (evita circularidades)
        from apps.denuncias.models import (
            Denuncia,
            DenunciaAnexo,
            DenunciaDocumentoImovel,
            DenunciaApontamento,
            DenunciaApontamentoAnexo,
            DenunciaHistorico,
        )
        from apps.notificacoes.models import Notificacao, NotificacaoAnexo
        from apps.autoinfracao.models import AutoInfracao
        try:
            from apps.autoinfracao.models import AutoInfracaoAnexo, AutoInfracaoMultaItem
        except Exception:
            AutoInfracaoAnexo = None
            AutoInfracaoMultaItem = None

        # QuerySets
        den_qs = Denuncia.objects.filter(**filters)
        den_ax_qs = DenunciaAnexo.objects.filter(denuncia__in=den_qs)
        den_doc_qs = DenunciaDocumentoImovel.objects.filter(denuncia__in=den_qs)
        den_ap_qs = DenunciaApontamento.objects.filter(denuncia__in=den_qs)
        den_ap_ax_qs = DenunciaApontamentoAnexo.objects.filter(apontamento__in=den_ap_qs)
        den_hist_qs = DenunciaHistorico.objects.filter(denuncia__in=den_qs)

        ntf_qs = Notificacao.objects.filter(**filters)
        ntf_ax_qs = NotificacaoAnexo.objects.filter(notificacao__in=ntf_qs)

        aif_qs = AutoInfracao.objects.filter(**filters)
        aif_ax_qs = AutoInfracaoAnexo.objects.filter(auto_infracao__in=aif_qs) if AutoInfracaoAnexo else None
        aif_multa_qs = AutoInfracaoMultaItem.objects.filter(auto_infracao__in=aif_qs) if AutoInfracaoMultaItem else None

        # DRY-RUN: mostra contagens
        self.stdout.write(self.style.WARNING("=== DRY-RUN ===" if not confirm else "=== EXECUTANDO PURGE ==="))
        self.stdout.write(f"Prefeitura alvo: {'TODAS' if not pref_id else pref_id}")
        self.stdout.write("-- Denúncias --")
        self.stdout.write(f"Denúncias: {self._count_qs(den_qs)}")
        self.stdout.write(f"Denúncia Anexos: {self._count_qs(den_ax_qs)}")
        self.stdout.write(f"Denúncia Docs Imóvel: {self._count_qs(den_doc_qs)}")
        self.stdout.write(f"Denúncia Apontamentos: {self._count_qs(den_ap_qs)}")
        self.stdout.write(f"Denúncia Apont. Anexos: {self._count_qs(den_ap_ax_qs)}")
        self.stdout.write(f"Denúncia Histórico: {self._count_qs(den_hist_qs)}")
        self.stdout.write("-- Notificações --")
        self.stdout.write(f"Notificações: {self._count_qs(ntf_qs)}")
        self.stdout.write(f"Notificação Anexos: {self._count_qs(ntf_ax_qs)}")
        self.stdout.write("-- Autos de Infração --")
        self.stdout.write(f"Autos: {self._count_qs(aif_qs)}")
        if aif_multa_qs is not None:
            self.stdout.write(f"AIF Multas: {self._count_qs(aif_multa_qs)}")
        if aif_ax_qs is not None:
            self.stdout.write(f"AIF Anexos: {self._count_qs(aif_ax_qs)}")

        if not confirm:
            self.stdout.write(self.style.WARNING("Nada foi apagado. Use --yes para executar."))
            return

        with transaction.atomic():
            # Remove arquivos primeiro
            for ax in den_ax_qs.iterator():
                self._del_file(ax.arquivo)
            for doc in den_doc_qs.iterator():
                self._del_file(doc.arquivo)
            for ax in den_ap_ax_qs.iterator():
                self._del_file(ax.arquivo)
            for ax in ntf_ax_qs.iterator():
                self._del_file(ax.arquivo)
            if aif_ax_qs is not None:
                for ax in aif_ax_qs.iterator():
                    self._del_file(ax.arquivo)

            # Apaga registros em ordem segura
            if aif_multa_qs is not None:
                aif_multa_qs.delete()
            if aif_ax_qs is not None:
                aif_ax_qs.delete()
            aif_qs.delete()

            ntf_ax_qs.delete()
            ntf_qs.delete()

            den_ap_ax_qs.delete()
            den_ap_qs.delete()
            den_doc_qs.delete()
            den_ax_qs.delete()
            den_hist_qs.delete()
            den_qs.delete()

        # Limpa pastas de mídia específicas (não mexe em outras)
        from django.conf import settings
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root and os.path.isdir(media_root):
            for sub in ("denuncias", "notificacoes", "autoinfracao"):
                path = os.path.join(media_root, sub)
                if os.path.isdir(path):
                    try:
                        shutil.rmtree(path)
                    except Exception:
                        pass

        self.stdout.write(self.style.SUCCESS("Purge concluído."))

