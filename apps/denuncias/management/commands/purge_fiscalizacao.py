from django.core.management.base import BaseCommand
from django.db import transaction

# Denúncias
from apps.denuncias.models import (
    Denuncia,
    DenunciaAnexo,
    DenunciaDocumentoImovel,
    DenunciaHistorico,
    DenunciaApontamento,
    DenunciaApontamentoAnexo,
)

# Notificações
from apps.notificacoes.models import (
    Notificacao,
    NotificacaoAnexo,
)

# Autos de Infração e Medidas
from apps.autoinfracao.models import (
    AutoInfracao,
    AutoInfracaoAnexo,
    Embargo,
    EmbargoAnexo,
    Interdicao,
    InterdicaoAnexo,
)


def _delete_files(qs, file_attr="arquivo"):
    total = 0
    for obj in qs.iterator():
        f = getattr(obj, file_attr, None)
        try:
            if f and getattr(f, 'name', None):
                f.delete(save=False)
                total += 1
        except Exception:
            # Nunca abortar por falha de remoção de arquivo
            pass
    # Apaga registros após os arquivos
    qs.delete()
    return total


class Command(BaseCommand):
    help = "Remove TODOS os dados operacionais (Denúncias, Notificações, AIFs, Medidas) e seus anexos (fotos/documentos). Mantém cadastros básicos."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirma a operação sem perguntar")
        parser.add_argument("--dry-run", action="store_true", help="Apenas mostra quantidades; não exclui nada")

    def handle(self, *args, **opts):
        confirm = opts.get("yes")
        dry = opts.get("dry_run")

        # Contagens (para mostrar antes)
        counts = {
            "den_ap_anexos": DenunciaApontamentoAnexo.objects.count(),
            "den_ap": DenunciaApontamento.objects.count(),
            "den_anexos": DenunciaAnexo.objects.count(),
            "den_docs": DenunciaDocumentoImovel.objects.count(),
            "den_hist": DenunciaHistorico.objects.count(),
            "den": Denuncia.objects.count(),
            "not_anexos": NotificacaoAnexo.objects.count(),
            "not": Notificacao.objects.count(),
            "aif_anexos": AutoInfracaoAnexo.objects.count(),
            "emb_anexos": EmbargoAnexo.objects.count(),
            "itd_anexos": InterdicaoAnexo.objects.count(),
            "emb": Embargo.objects.count(),
            "itd": Interdicao.objects.count(),
            "aif": AutoInfracao.objects.count(),
        }

        self.stdout.write(self.style.WARNING("Resumo atual para apagar:"))
        self.stdout.write(f"- Denúncias: {counts['den']} (hist: {counts['den_hist']}, docs: {counts['den_docs']}, fotos: {counts['den_anexos']}, apontamentos: {counts['den_ap']}, fotos apont.: {counts['den_ap_anexos']})")
        self.stdout.write(f"- Notificações: {counts['not']} (anexos: {counts['not_anexos']})")
        self.stdout.write(f"- AIFs: {counts['aif']} (anexos: {counts['aif_anexos']})")
        self.stdout.write(f"- Embargos: {counts['emb']} (anexos: {counts['emb_anexos']}) | Interdições: {counts['itd']} (anexos: {counts['itd_anexos']})")

        if dry:
            self.stdout.write(self.style.SUCCESS("(dry-run) Nada foi excluído."))
            return

        if not confirm:
            ans = input("CONFIRMAR a exclusão IRREVERSÍVEL desses dados? (digite 'SIM' para continuar): ")
            if ans.strip().upper() != "SIM":
                self.stdout.write(self.style.WARNING("Abortado pelo usuário."))
                return

        with transaction.atomic():
            # Anexos: remover arquivos antes (ordem: mais específicos -> gerais)
            self.stdout.write("Removendo anexos de Apontamentos de Denúncia...")
            _delete_files(DenunciaApontamentoAnexo.objects.all())
            self.stdout.write("Removendo Apontamentos de Denúncia...")
            DenunciaApontamento.objects.all().delete()

            self.stdout.write("Removendo anexos de Denúncia (fotos)...")
            _delete_files(DenunciaAnexo.objects.all())
            self.stdout.write("Removendo documentos de imóvel (arquivos)...")
            _delete_files(DenunciaDocumentoImovel.objects.all())
            self.stdout.write("Removendo históricos de Denúncia...")
            DenunciaHistorico.objects.all().delete()

            self.stdout.write("Removendo anexos de Notificação...")
            _delete_files(NotificacaoAnexo.objects.all())

            self.stdout.write("Removendo anexos de AIF/Embargo/Interdição...")
            _delete_files(AutoInfracaoAnexo.objects.all())
            _delete_files(EmbargoAnexo.objects.all())
            _delete_files(InterdicaoAnexo.objects.all())

            self.stdout.write("Removendo Embargos/Interdições...")
            Embargo.objects.all().delete()
            Interdicao.objects.all().delete()

            self.stdout.write("Removendo AIFs...")
            AutoInfracao.objects.all().delete()

            self.stdout.write("Removendo Notificações...")
            Notificacao.objects.all().delete()

            self.stdout.write("Removendo Denúncias...")
            Denuncia.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Dados de fiscalização apagados com sucesso (Denúncias/Notificações/AIFs/Medidas e anexos)."))

