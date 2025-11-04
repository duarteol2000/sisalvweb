from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.urls import resolve

from apps.usuarios.models import AuditLog


def _get_client_ip(req):
    xff = req.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return req.META.get('REMOTE_ADDR')


class AuditMiddleware(MiddlewareMixin):
    """
    Middleware simples de auditoria de acessos e ações.
    - Registra VIEW para GET em rotas dos módulos
    - Classifica PRINT/CREATE/UPDATE/DELETE por heurística no path
    Não afeta performance de forma significativa e ignora arquivos estáticos/mídia/admin.
    """

    AUDIT_PREFIXES = ('/denuncias', '/notificacoes', '/autoinfracao', '/cadastros', '/prefeituras')
    IGNORE_PREFIXES = ('/static/', '/media/', '/admin/', '/__debug__')

    def process_response(self, request, response):
        try:
            path = request.path or ''
            if any(path.startswith(p) for p in self.IGNORE_PREFIXES):
                return response

            if not any(path.startswith(p) for p in self.AUDIT_PREFIXES):
                return response

            user = getattr(request, 'user', None)
            if not (user and user.is_authenticated):
                return response

            metodo = request.method.upper()
            acao = 'VIEW' if metodo == 'GET' else 'OTHER'
            lower_path = path.lower()
            if 'imprimir' in lower_path:
                acao = 'PRINT'
            elif metodo in ('POST', 'PUT', 'PATCH'):
                if any(k in lower_path for k in ('cadastrar', 'criar', 'nova', 'novo')):
                    acao = 'CREATE'
                elif any(k in lower_path for k in ('editar', 'update')):
                    acao = 'UPDATE'
                elif any(k in lower_path for k in ('excluir', 'apagar', 'deletar', 'delete')):
                    acao = 'DELETE'
                elif 'vincular' in lower_path:
                    acao = 'LINK'
                elif 'desvincular' in lower_path:
                    acao = 'UNLINK'
            elif metodo == 'DELETE':
                acao = 'DELETE'

            try:
                match = resolve(path)
                app_label = getattr(match, 'app_name', '') or ''
                view_mod = match.func.__module__ if hasattr(match, 'func') else ''
                recurso = ''
                if path.startswith('/denuncias'):
                    recurso = 'denuncias'
                elif path.startswith('/notificacoes'):
                    recurso = 'notificacoes'
                elif path.startswith('/autoinfracao'):
                    recurso = 'autoinfracao'
                elif path.startswith('/cadastros'):
                    recurso = 'cadastros'
                elif path.startswith('/prefeituras'):
                    recurso = 'prefeituras'
                object_id = ''
                # Tenta captar PK comum
                for key in ('pk', 'id', 'den_pk', 'notif_pk', 'aif_pk'):
                    if key in match.kwargs:
                        object_id = str(match.kwargs[key])
                        break
                extra = None
                if metodo == 'GET':
                    params = dict(request.GET)
                    if params:
                        extra = {'params': {k: v[:1] if isinstance(v, list) else v for k, v in params.items()}}
                else:
                    keys = list(request.POST.keys())
                    if keys:
                        extra = {'post_keys': keys[:50]}

                AuditLog.objects.create(
                    usuario=user,
                    prefeitura_id=request.session.get('prefeitura_id'),
                    acao=acao,
                    recurso=recurso,
                    app_label=app_label or view_mod,
                    model='',
                    object_id=object_id,
                    url=path,
                    metodo=metodo,
                    ip=_get_client_ip(request),
                    user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
                    extra=extra,
                    criado_em=timezone.now(),
                )
            except Exception:
                # Nunca quebrar a resposta por causa de auditoria
                pass
        finally:
            return response

