from django.utils import timezone
from django.urls import resolve

from apps.usuarios.models import AuditLog


def _get_client_ip(req):
    xff = req.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return req.META.get('REMOTE_ADDR')


def log_event(request, acao: str, instance=None, recurso: str | None = None, extra: dict | None = None):
    """
    Registra um evento de auditoria com precisão do objeto (app/model/pk).
    - acao: 'VIEW'|'CREATE'|'UPDATE'|'DELETE'|'PRINT'|'LINK'|'UNLINK'|'OTHER'
    - instance: objeto salvo/de referência (usa _meta para app/model e pk)
    - recurso: rótulo do módulo (se omitido, tenta pelo app_label/path)
    - extra: dict opcional com metadados (será truncado pelo DB se muito grande)
    """
    try:
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return

        app_label = ''
        model_name = ''
        object_id = ''
        if instance is not None:
            try:
                app_label = instance._meta.app_label
                model_name = instance._meta.model_name
                object_id = str(getattr(instance, 'pk', '') or '')
            except Exception:
                pass

        # Recurso por prioridade: parâmetro → app_label → path
        if not recurso:
            recurso = app_label or ''
            if not recurso:
                path = request.path or ''
                for p in ('denuncias', 'notificacoes', 'autoinfracao', 'cadastros', 'prefeituras'):
                    if path.startswith('/' + p):
                        recurso = p
                        break

        AuditLog.objects.create(
            usuario=user,
            prefeitura_id=request.session.get('prefeitura_id'),
            acao=acao,
            recurso=recurso or '',
            app_label=app_label,
            model=model_name,
            object_id=object_id,
            url=request.path or '',
            metodo=request.method.upper(),
            ip=_get_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
            extra=extra,
            criado_em=timezone.now(),
        )
    except Exception:
        # Auditoria nunca deve quebrar o fluxo de negócio
        pass

