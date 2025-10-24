# SISALV WEB

Sistema de apoio à fiscalização municipal (denúncias, notificações, autos de infração, embargos e interdições), com foco em fluxo simples, emissão de documentos e acompanhamento.

## Comece Aqui
- Guia rápido (ambiente local + Git): docs/guia_local_e_git.md
- Resumo das mudanças recentes (roadmap): https://github.com/duarteol2000/sisalvweb/issues/1

## Requisitos
- Python 3.11+
- SQLite (padrão) ou outro banco suportado pelo Django

## Instalação rápida
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
Acesse: http://127.0.0.1:8000/

## Estrutura (resumo)
- apps/
  - autoinfracao/ (AIF, Embargo, Interdição)
  - denuncias/
  - notificacoes/
  - usuarios/
- templates/ (base e páginas)
- static/ (CSS/JS/Imagens)
- docs/ (documentos, guias)

## Licença
Defina aqui a licença do projeto (se houver). Caso não definida, o código permanece sem licença explícita.
