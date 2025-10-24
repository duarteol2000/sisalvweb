# Guia rápido: ambiente local e fluxo Git

Este guia reúne os passos práticos para rodar o projeto em outra máquina (ex.: em casa) e um fluxo Git simples para trabalhar com segurança.

## 1) Clonar e preparar o ambiente

1. Clonar o repositório
   - `git clone https://github.com/duarteol2000/sisalvweb.git`
   - `cd sisalvweb`

2. Criar venv e instalar dependências
   - Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`
   - Windows (PowerShell): `py -3 -m venv .venv; .venv\Scripts\Activate.ps1`
   - Instalar: `pip install -r requirements.txt`

3. Banco de dados/migrações
   - `python manage.py migrate`
   - (Opcional) Criar admin: `python manage.py createsuperuser`

4. Rodar o servidor
   - `python manage.py runserver`
   - Acesse: `http://127.0.0.1:8000/`

Dicas
- Se precisar de dados de exemplo, rode as migrações: o projeto contém seeds básicos para Tipos/Enquadramentos.
- Caso use `.env`, crie o arquivo copiando de um exemplo (se existir) e ajuste credenciais locais.

## 2) Atualizar o projeto local

- Puxar as últimas alterações antes de começar:
  - `git fetch origin`
  - `git pull --rebase origin main`

## 3) Fluxo Git recomendado (simples)

Conceitos
- Issue: tarefa/bug/ideia no GitHub.
- PR (Pull Request): proposta de merge de uma branch para outra.
- Tag/Release: ponto marcado no histórico (publicação).

Fluxo
1. Crie uma issue no GitHub descrevendo a tarefa.
2. Crie uma branch de trabalho:
   - `git switch -c feature/minha-tarefa`
3. Faça commits pequenos e frequentes:
   - `git add -A`
   - `git commit -m "feat: descrição curta do que mudou"`
4. Publique sua branch:
   - `git push -u origin feature/minha-tarefa`
5. Abra um PR no GitHub (feature → main). Use “Closes #N” no texto para fechar a issue ao fazer merge.
6. Depois do merge, atualize sua `main` local:
   - `git checkout main && git pull --rebase origin main`

## 4) Comandos essenciais

- Status e diferenças
  - `git status -sb`
  - `git diff` (mudanças não staged)
  - `git diff --staged` (mudanças staged)
- Branches
  - `git branch --show-current`
  - `git switch -c feature/x` (criar e mudar)
  - `git switch main` (voltar)
- Atualizar e publicar
  - `git fetch origin`
  - `git pull --rebase origin main`
  - `git push origin <branch>`
- Histórico
  - `git log --oneline --graph --decorate -n 20`

## 5) Tags e Releases

- Criar tag anotada e enviar:
  - `git tag -a v0.1.0 -m "v0.1.0: notas"`
  - `git push origin v0.1.0`
- Criar “Release” no GitHub a partir da tag (interface web), incluindo notas/changelog.

## 6) Push com token (HTTPS)

Se o Git solicitar usuário/senha:
- Username: seu usuário GitHub (ex.: `duarteol2000`)
- Password: cole o **PAT** (Personal Access Token) com permissão “Contents: Read and write”.

Gerar PAT
- GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate.
- Repository access: selecione `sisalvweb`.
- Permissions: **Contents: Read and write** (e Metadata: Read-only).

Dica de segurança
- Evite colocar o token na URL do remote.
- Para “lembrar” o token nesta máquina (se for segura): `git config --global credential.helper store`.
- Revogue tokens antigos em: Settings → Developer settings → Personal access tokens.

## 7) Erros comuns e soluções rápidas

- 403 ao fazer push: verifique o escopo do PAT (Contents: Read and write) e se a branch tem proteção.
- Conflitos ao puxar (pull/rebase): abra os arquivos com conflito, resolva, depois `git add` e `git rebase --continue` (ou `git merge --continue`).
- Quer descartar mudanças locais sem apagar arquivos: `git restore --source=HEAD -- .` (cuidado: perde alterações não commitadas).

## 8) Convenções de commit (sugestão)

Use prefixos curtos:
- `feat:` nova funcionalidade
- `fix:` correção
- `docs:` documentação
- `refactor:` refatoração sem mudar comportamento
- `style:` formatação/estilo
- `chore:` tarefas auxiliares

---

Qualquer dúvida, abra uma issue no GitHub do projeto descrevendo o que precisa.
