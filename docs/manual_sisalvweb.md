# Manual do SISALV WEB (Passo a passo para usuários)

Este manual foi escrito para usuários iniciantes utilizarem o SISALV WEB no dia a dia: como entrar, cadastrar, consultar, anexar fotos, gerar documentos e emitir relatórios.

Observação: campos marcados como (obrigatório) devem ser preenchidos para salvar.

---

## 1) Acesso e Perfis

- Endereço: seu domínio (ex.: `https://<seu-subdominio>.ngrok-free.dev/`).
- Login: e‑mail + senha + Código IBGE da prefeitura.
- Perfis de usuário (simplificado):
  - ADMIN/FISCAL: podem cadastrar/editar, anexar fotos, gerar documentos.
  - VISUAL: apenas consulta.

Dica de segurança: sempre use o endereço HTTPS que foi liberado nos `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`.

---

## 2) Conceitos rápidos

- Denúncia (entrada): ponto de partida do processo, normalmente criada internamente.
- Notificação (NTF): documento educativo/preventivo; pode nascer da Denúncia ou isolado.
- Auto de Infração (AIF): documento sancionatório; pode nascer de Notificação ou isolado.
- Medidas (Embargo/Interdição): derivam do AIF.
- Apontamento de Campo: registro leve de fotos/observações associado à Denúncia, pensado para uso em tablet.
- Galeria de Fotos (unificada): telas mostram fotos herdadas de documentos relacionados, sem duplicar.

---

## 3) Cadastro de Denúncia

Menu: Fiscalização → 📣 Denúncias → “Cadastrar”.

Campos principais (obrigatórios):
- Local da ocorrência: Logradouro, Bairro, Cidade, UF (obrigatórios); Nº/Complemento/CEP (opcionais)
- Descrição detalhada (obrigatório)
- Denunciado: “Nome/Razão” (se não souber, use o endereço ou “A DEFINIR”)
- Geolocalização (Latitude/Longitude): opcional; aceita vírgula (ex.: -3,732700 / -38,527000)

Anexos (opcionais):
- Fotos: até 4 por Denúncia; o sistema otimiza automaticamente.
- Documentos do imóvel: escolha “Tipo” e envie o arquivo.

Salvar: clique em “📌 Salvar”.

Depois de salvar, você pode vincular Pessoa/Imóvel e gerar documentos.

---

## 4) Editar Denúncia (básico e completo)

- Detalhe da Denúncia → botões:
  - ✏️ Editar (básico): altera campos principais e permite anexar fotos/documentos.
  - 🛠️ Editar (completo): exibe todos os campos; permite anexar fotos (até 4 por envio) e remover anexos existentes.

Procedência (importante):
- Antes de gerar Notificação ou AIF, você pode marcar “Procede” ou “Não procede”.
- Após gerar Notificação ou AIF, a procedência é travada (não pode mais alterar).
- Ao gerar NTF/AIF a partir da Denúncia, a procedência é marcada automaticamente como PROCEDE e o histórico registra a ação.

---

## 5) Apontamento de Campo (tablet)

Uso: quando o fiscal precisa registrar fotos/observações no local, rapidamente, sem editar toda a Denúncia.

- No Detalhe da Denúncia → 📸 “Apontamento de Campo”.
- Observação (até 280 caracteres), Fotos (até 4, ~100 KB cada).
- Opção “Atualizar geolocalização da Denúncia”: ao marcar, abre mapa para selecionar o ponto.
- As fotos do Apontamento aparecem automaticamente na Galeria da Denúncia/NTF/AIF (sem duplicar).

---

## 6) Gerar Notificação (a partir da Denúncia)

- No Detalhe da Denúncia → 📄 “Gerar Notificação”.
- O sistema preenche dados com base na Denúncia e vínculos (Pessoa/Imóvel) quando existirem.
- Campos obrigatórios típicos da Notificação:
  - Pessoa: Tipo (PF/PJ), Nome/Razão (obrigatórios)
  - Endereço do local: Logradouro, Bairro, Cidade, UF (obrigatórios)
  - Descrição da irregularidade (obrigatório)
- Fotos: até 4 por Notificação (opcional). O sistema otimiza e limita tamanho (~100 KB cada).
- Impressão: no detalhe da Notificação → “Imprimir”.

Galeria de fotos (visualização):
- Mostra fotos da Denúncia (e Apontamentos) + fotos próprias da Notificação (sem duplicar).

---

## 7) Gerar Auto de Infração (a partir da Notificação ou direto)

- Do Detalhe da Notificação → “Gerar Auto de Infração”, ou menu AIF → “Cadastrar”.
- Campos obrigatórios típicos do AIF:
  - Pessoa: Tipo (PF/PJ), Nome/Razão (obrigatórios)
  - Endereço do local: Logradouro, Bairro, Cidade, UF (obrigatórios)
  - Descrição/Constatação (obrigatório)
- Prazos/valores: informe prazos e valores; é possível homologar itens de multa depois.
- Fotos: até 4 por AIF (opcional), com otimização (~100 KB).
- Impressão: “Imprimir” no detalhe do AIF.

Galeria de fotos (visualização):
- Se veio de NTF: vê fotos da Notificação + (herdadas) Denúncia/Apontamentos + fotos do AIF (sem duplicar).
- Se nasceu direto em AIF: vê apenas as próprias, até que seja vinculado a NTF/Denúncia.

---

## 8) Medidas (Embargo / Interdição)

- No Detalhe do AIF → “Gerar Embargo/Interdição”.
- Preencha dados, prazos e anexos quando necessário (ex.: Alvará para regularização).
- Fotos: seguem a regra de otimização (~100 KB), com limite prático por processo.

---

## 9) Galeria de Fotos (unificada, sem duplicar)

- Denúncia: fotos próprias + fotos de Apontamentos.
- Notificação: fotos da Denúncia/Apontamentos + fotos próprias da Notificação.
- AIF: fotos da Notificação + Denúncia/Apontamentos + fotos próprias do AIF.
- Deduplicação: fotos com mesmo hash são mostradas apenas uma vez.
- Exclusão: só é possível remover fotos pertencentes à entidade atual (as herdadas mostram a origem, sem botão de excluir).

Limites e regras de arquivo:
- Até 4 fotos por documento (Denúncia, Notificação, AIF) e por Apontamento.
- Tamanho por foto: ~95 KB alvo (máx. 100 KB), largura máxima de 1000 px.
- O sistema converte imagens para JPG, calcula hash e guarda dimensões.

---

## 10) Consultas — Mapa

Menu: Consultas → 🗺️ Mapa
- Mostra pontos no mapa com aglomeração (Leaflet). Centro do mapa usa a geolocalização da Prefeitura.
- Filtros (barra superior): tipo (Denúncia/Notificação/AIF/ALL), ano, protocolo, área visível (bbox).
- Clique nos pontos para abrir os documentos relacionados.

---

## 11) Relatórios

1) Operacional — Entradas, Saídas e Processos Ativos
- Menu: Relatórios → 📊 Operacional
- Período: mês corrente (padrão) ou intervalo personalizado.
- Tabela: Entradas (criados), Saídas (encerrados) e Processos Ativos (saldo) por módulo.
- CSV: botão “Exportar CSV”.
- Gráfico: barras por módulo com rótulos numéricos.

2) Arrecadação AIF — Mensal
- Menu: Relatórios → 💵 Arrecadação AIF (Mensal)
- Período: ano corrente (padrão) ou intervalo personalizado.
- Filtros: Status (AIF) e Forma de Pagamento (para pagos).
- Séries mensais:
  - Multa aplicada (valor de infração)
  - Valor homologado
  - Valor pago
- Tabela mensal + totais e “Ticket Médio Pago”.
- CSV e impressão com layout de relatório.

---

## 12) Impressões

- Denúncia/Notificação/AIF têm páginas próprias de impressão com cabeçalho e logo.
- Mapa e geolocalização aparecem quando disponíveis.

---

## 13) Dicas e erros comuns

- “Host inválido” ao acessar: confira se está no domínio HTTPS correto.
- “CSRF failed”: reabra a página no domínio HTTPS e tente novamente.
- Foto muito grande: o sistema otimiza; se continuar rejeitando, verifique se o arquivo ultrapassa 100 KB após compressão (casos raros).
- Procedência bloqueada: após gerar Notificação ou AIF a partir da Denúncia, a procedência fica travada.

---

## 14) Limpeza de dados para testes (opcional)

Para ambiente de testes, existe um comando para “zerar” os dados operacionais (não apaga cadastros básicos):

```
python manage.py purge_fiscalizacao --dry-run   # mostra quantidades
python manage.py purge_fiscalizacao --yes       # executa
```

---

## 15) Suporte e Auditoria

- O sistema registra ações (login, visualização, criação, atualização, impressão), vínculo à Prefeitura e IP/Agente.
- Em caso de dúvidas, registre exemplos (protocolo e período) para conferência.

---

## Anexo A — Campos obrigatórios (resumo)

- Denúncia: Local (Logradouro, Bairro, Cidade, UF), Descrição; Denunciado Nome/Razão (use endereço ou “A DEFINIR” se necessário).
- Notificação: Pessoa (Tipo, Nome/Razão), Endereço (Logradouro, Bairro, Cidade, UF), Descrição.
- AIF: Pessoa (Tipo, Nome/Razão), Endereço (Logradouro, Bairro, Cidade, UF), Descrição.

Obs.: Documentos e fotos são opcionais, mas fortemente recomendados quando aplicável.

---

Este manual acompanha a versão atual do SISALV WEB. Ajustes pontuais podem alterar nomes de campos ou telas; sempre que necessário, atualizaremos este documento.

