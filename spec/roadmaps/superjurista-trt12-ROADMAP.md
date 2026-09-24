# Roteiro de desenvolvimento: SuperJurista TRT12

**Situação:** ativo e aprovado
**Versão:** 0.50.0
**Data:** 2026-09-22
**Plano arquitetural:** [`superjurista-trt12-first-instance-BLUEPRINT.md`](../blueprints/superjurista-trt12-first-instance-BLUEPRINT.md)

---

## 1. Finalidade

Este roteiro mede capacidades entregues, não atividade. Um item só contribui
para o avanço depois de passar em seu critério de aceite e ter as evidências
vinculadas neste documento.

Ele responde a quatro perguntas operacionais:

1. Qual é a próxima entrega delimitada?
2. Quanta capacidade validada já existe?
3. Quais evidências sustentam o percentual informado?
4. O que impede o próximo marco?

---

## 2. Estrutura do programa

O programa tem três frentes medidas separadamente:

| Frente | Resultado | Peso no programa | Situação inicial |
|---|---|---:|---:|
| A | Produto mínimo validado para o primeiro grau do TRT12 | 60% | 0/100 pontos aceitos |
| B | Extensão validada para o segundo grau do TRT12 | 25% | 0/100 pontos aceitos |
| C | Comprovação de portabilidade para outro TRT | 15% | 0/100 pontos aceitos |

### 2.1 Fórmula do avanço do programa

```text
PROGRAM_PROGRESS =
    0.60 × TRACK_A_PROGRESS
  + 0.25 × TRACK_B_PROGRESS
  + 0.15 × TRACK_C_PROGRESS
```

Cada frente recebe de 0 a 100 pontos. O programa chega a 60% quando o produto
mínimo do primeiro grau do TRT12 é integralmente aceito, mesmo que o segundo
grau e a portabilidade ainda não tenham começado. Assim, o escopo futuro não
oculta se o primeiro alvo utilizável está pronto.

### 2.2 Situação atual

```text
Frente A — TRT12, primeiro grau: 50/100 pontos aceitos
Frente B — TRT12, segundo grau:    0/100 pontos aceitos
Frente C — outros TRTs:           0/100 pontos aceitos
Avanço ponderado do programa:    30,0%
Candidatos em revisão na frente A: 4/100 pontos
```

O usuário aprovou expressamente o plano arquitetural e este roteiro em
2026-09-21. Por isso, `ARC-01` está aceito e soma três pontos. Os demais pontos
candidatos aparecem separadamente e não entram na fórmula de avanço antes de
passarem em seus critérios técnicos.

---

## 3. Regras de situação e evidência

### 3.1 Valores de situação

| Situação | Significado | Pontos obtidos |
|---|---|---:|
| `PLANNED` | Definido, mas não iniciado | 0 |
| `IN_PROGRESS` | Há trabalho realizado, mas o critério de aceite não passou | 0 |
| `BLOCKED` | Depende de uma decisão ou condição identificada | 0 |
| `IN_REVIEW` | Há evidência candidata em avaliação | 0 |
| `ACCEPTED` | O critério passou e a evidência está vinculada | Peso integral do item |
| `REOPENED` | Uma evidência anteriormente aceita foi invalidada | 0 até novo aceite |

Não há percentuais parciais por item: eles são subjetivos e fáceis de distorcer.
O avanço incremental decorre de itens pequenos que podem ser aceitos de forma
independente.

### 3.2 Evidências exigidas

Cada item `ACCEPTED` deve registrar:

- commit ou solicitação de alteração;
- arquivos entregues;
- comandos de validação e resultados;
- caso sintético, conjunto de dados ou amostra de processos utilizados;
- registro de revisão ou aprovação quando houver julgamento humano;
- limitações conhecidas fora do escopo do item.

Documentação, por si só, não demonstra o comportamento em execução. Testes
sintéticos não comprovam adequação jurídica histórica. Um caso histórico bem
sucedido não demonstra a reprodutibilidade de um adaptador.

### 3.3 Regra de reabertura

Um item aceito volta a `REOPENED` quando:

- uma regressão invalida sua evidência de aceite;
- um contrato muda de forma incompatível;
- uma fonte oficial ou um endpoint muda de forma relevante;
- um defeito crítico é atribuído ao item.

Os pontos são retirados até que o item passe novamente em seu critério.

---

## 4. Frente A — produto mínimo do primeiro grau do TRT12

A frente A contém exatamente 100 pontos.

### 4.1 Resumo dos pacotes de trabalho

| Pacote de trabalho | Peso | Aceitos | Situação |
|---|---:|---:|---|
| FND — base técnica | 8 | 8 | `ACCEPTED` |
| ARC — arquitetura e contratos | 12 | 12 | `ACCEPTED` |
| PJE — obtenção de dados do PJe-JT do TRT12 | 18 | 0 | `IN_PROGRESS` |
| DOM — capacidades do domínio trabalhista | 20 | 0 | `IN_PROGRESS` |
| JUR — pesquisa em fontes de autoridade | 15 | 11 | `IN_PROGRESS` |
| PIP — pipeline e verificações de ponta a ponta | 15 | 15 | `ACCEPTED` |
| VAL — validação histórica | 10 | 2 | `IN_PROGRESS` |
| OPS — preparação do piloto controlado | 2 | 2 | `ACCEPTED` |
| **Total** | **100** | **50** |  |

### 4.2 Fortalecimento da base — 8 pontos

O primeiro pacote de implementação é `PKG-01 — base do fork e contrato para dois
ambientes de execução`. Ele começa por `FND-04` e produz as evidências necessárias
para adaptar o fork sem reescrevê-lo.

`PKG-01` entrega:

- um inventário dos comandos, agentes, skills, scripts e provedores existentes;
- a classificação preservar/adaptar/substituir/retirar de cada componente abrangido;
- testes de caracterização do comportamento determinístico reutilizável;
- um mapa dos vínculos específicos do Claude e de seus equivalentes no Codex;
- a delimitação proposta do manifesto de pipeline independente do ambiente;
- um teste mínimo que demonstra a mesma verificação compartilhada em Claude Code e Codex.

`PKG-01` é aceito quando `FND-04` passa e rende dois pontos da frente A. Isso
não significa que o pipeline trabalhista ou os ambientes completos estejam prontos.

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| FND-01 | Contrato de Python e dependências entre plataformas | 2 | `ACCEPTED` | Instalação e comandos documentados executam no macOS de destino; versão de Python é compatível com o código | [`runtime/python-contract.json`](../../runtime/python-contract.json), [`requirements`](../../requirements), [`scripts/check_python_contract.py`](../../scripts/check_python_contract.py), [`scripts/rehearse_target_host.py`](../../scripts/rehearse_target_host.py), `tests/test_python_contract.py` e `tests/test_target_host_rehearsal.py`; `.venv` limpa instalada no macOS com Python 3.12.14, MCP 1.30.0, dependências completas, Tesseract 5.5.3 com dados em português e Poppler 26.05. Os cinco servidores MCP preservados importaram e o conversor PDF reconheceu duas frases portuguesas congeladas em PDF sintético de uma página. O ensaio legível por máquina retornou `ready`, resumo `f925340cc3be04b5ef1dffe47ac317a64e0ec452eb6688f5350dc571647f1515`; cinco testes focados rejeitam dependências ausentes, versões não suportadas, OCR parcial, cobertura MCP incompleta e campos desconhecidos |
| FND-02 | Suíte automática de qualidade e entrada da CI | 2 | `ACCEPTED` | Um comando documentado executa formatação, análise estática e testes; CI ou execução limpa equivalente passa | [`scripts/quality_gate.py`](../../scripts/quality_gate.py), [execução 35657051683 do GitHub Actions](https://github.com/robertishimurasousa/superjurista-trt/actions/runs/35657051683), [`.github/workflows/quality.yml`](../../.github/workflows/quality.yml), `tests/test_quality_gate.py`; o comando compartilhado passou 130 testes locais e a execução remota passou em Python 3.9 e 3.10 no commit `cf78b5c` |
| FND-03 | Higiene de credenciais e dados processuais | 2 | `ACCEPTED` | Testes comprovam exclusão ou expurgo de `.env`, sessões, HARs, cookies, cabeçalhos e dados do processo | [`runtime/data-hygiene-contract.json`](../../runtime/data-hygiene-contract.json), [`scripts/check_data_hygiene.py`](../../scripts/check_data_hygiene.py), `tests/test_data_hygiene.py`, `.gitignore` e `scaffold/project-gitignore`; o controle integrado passou 130 testes e a revisão focada de 11 testes passou sem ler destinos externos de links simbólicos nem exibir segredos correspondentes |
| FND-04 | Inventário, caracterização e registro de reuso do fork para dois ambientes | 2 | `ACCEPTED` | Cada comando, agente, habilidade, script e provedor abrangido tem decisão preservar/adaptar/substituir/retirar; comportamento reutilizável tem evidência; vínculos Claude têm equivalentes Codex; ambos executam o mesmo controle básico | [`spec/inventory`](../inventory/README.md), [`runtime`](../../runtime/README.md), `tests/test_reuse_ledger.py`, `tests/test_runtime_contract.py`; suíte de 130 testes e revisão focada de reuso/execução passaram, com 107 componentes e nenhum sem classificação |

### 4.3 Arquitetura e contratos — 12 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| ARC-01 | Blueprint e roadmap ponderado por evidências | 3 | `ACCEPTED` | Usuário aprova expressamente escopo, sequência, limites de extensão e modelo de progresso | Aprovação registrada em 2026-09-21; esta revisão do blueprint e roadmap; histórico de commits do repositório |
| ARC-02 | Esquema versionado de perfil de tribunal e perfil TRT12 | 2 | `ACCEPTED` | Perfil válido passa; casos com dígito de ramo, adaptador, fonte ou assinatura inválidos bloqueiam | [`runtime/profiles`](../../runtime/profiles), [`scripts/validate_tribunal_profile.py`](../../scripts/validate_tribunal_profile.py), `tests/test_tribunal_profile.py`; controle compartilhado valida perfil canônico e dez testes focados cobrem primeiro grau válido, ramo, adaptador, fonte, assinatura, política de segurança e divergência de esquema |
| ARC-03 | Esquemas versionados de processo, classificação, linha do tempo, relatório, pedidos, provas, encaminhamento, precedentes, análise e dispositivo | 3 | `ACCEPTED` | Casos válidos e inválidos passam; política de versões e migração documentada | [`runtime/contracts`](../../runtime/contracts), [`scripts/validate_artifact_contracts.py`](../../scripts/validate_artifact_contracts.py), `tests/fixtures/contracts` e `tests/test_artifact_contracts.py`; dez casos válidos e 13 inválidos passam, incluindo custódia da linha do tempo, coerência de encaminhamento e completude da análise de mérito. Validação direta rejeita versões futuras; política exige esquemas aceitos imutáveis e migrações determinísticas não destrutivas |
| ARC-04 | Interfaces dos adaptadores de PJe e pesquisa | 2 | `ACCEPTED` | Testes de contrato executam com provedor simulado sem constantes TRT12 no núcleo | [`runtime/providers`](../../runtime/providers), [`scripts/provider_interfaces.py`](../../scripts/provider_interfaces.py), `tests/provider_fakes.py` e `tests/test_provider_interfaces.py`; seis testes com TRT99 cobrem dois fluxos positivos, capacidade ausente, cursor repetido, divergência SHA-256 e rejeição de fonte oficial sem HTTPS |
| ARC-05 | Manifesto de execução independente do ambiente e contratos Claude/Codex | 2 | `ACCEPTED` | Mesmo grafo de dados, dependências, limites de tentativa, caminhos e controles é resolvido nos dois ambientes | [`runtime/pipelines/trt12-first-instance.json`](../../runtime/pipelines/trt12-first-instance.json), [`scripts/resolve_runtime_pipeline.py`](../../scripts/resolve_runtime_pipeline.py), `tests/test_pipeline_resolution.py`; os dois ambientes obtêm o mesmo resumo do contrato |

### 4.4 Obtenção de dados do PJe-JT do TRT12 — 18 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| PJE-01 | Mapa HAR autorizado e sanitizado do primeiro grau do TRT12 | 3 | `IN_PROGRESS` | Mapa de endpoints, cookies/cabeçalhos, tarefas, documentos e falhas revisado, sem credenciais nos dados de teste | [`runtime/providers`](../../runtime/providers), [`scripts/sanitize_pje_har.py`](../../scripts/sanitize_pje_har.py), [`scripts/validate_pje_har_map.py`](../../scripts/validate_pje_har_map.py), `tests/test_pje_har_sanitizer.py` e `tests/test_pje_har_map_review.py`; 13 testes sintéticos comprovam expurgo determinístico, classificação dos endpoints, mapeamento de falhas, integridade, lacunas de revisão, vínculo ao alvo e bloqueio seguro. Cobertura funcional ou de autenticação ausente impede prontidão; falhas não observadas naturalmente permanecem em `observed_failure_gaps`. O operador não deve provocar erro 401, tempo esgotado ou falha do provedor para obter evidência. Ainda faltam captura TRT12 autorizada e revisão humana do mapa |
| PJE-02 | Adaptador de sessão e autenticação | 4 | `IN_PROGRESS` | Detecta sessão válida, expirada, com MFA obrigatório ou não autorizada sem revelar segredos | [`runtime/providers/pje-session-contract.json`](../../runtime/providers/pje-session-contract.json), [`scripts/pje_session_adapter.py`](../../scripts/pje_session_adapter.py) e `tests/test_pje_session_adapter.py`; nove testes sintéticos TRT99 cobrem estados válidos, expirados, MFA, não autorizados, conflitantes e com evidência insuficiente, além de exigir capacidade e saída sem segredos. Ainda faltam verificação concreta TRT12 e evidência autorizada de estados reais |
| PJE-03 | Descoberta de tarefas e processos | 3 | `IN_PROGRESS` | Lista de modo reproduzível a fila autorizada e identifica processos sem perda silenciosa na paginação | [`runtime/providers/pje-task-discovery-contract.json`](../../runtime/providers/pje-task-discovery-contract.json), [`scripts/pje_task_discovery.py`](../../scripts/pje_task_discovery.py) e `tests/test_pje_task_discovery.py`; oito testes sintéticos TRT99 cobrem paginação completa em dois níveis, fila vazia, cursores repetidos, processos duplicados, região CNJ divergente, exigência de capacidade e saída sem segredos. Ainda faltam adaptador concreto TRT12 e ensaio autorizado da fila |
| PJE-04 | Índice e download de documentos | 4 | `IN_PROGRESS` | Produz IDs estáveis, resumos criptográficos, metadados e lacunas explícitas para o ensaio | [`runtime/providers/document-index-contract.json`](../../runtime/providers/document-index-contract.json), [`scripts/acquire_pje_documents.py`](../../scripts/acquire_pje_documents.py) e `tests/test_pje_document_acquisition.py`; oito testes sintéticos TRT99 cobrem índice e download determinísticos em duas páginas, subconjuntos solicitados, metadados estáveis, custódia SHA-256, documentos ausentes, indisponibilidade explícita, IDs duplicados, cursores repetidos, validação de IDs e saída válida conforme esquema. Ainda faltam adaptador TRT12 vinculado à captura revisada e ensaio documental fechado e autorizado |
| PJE-05 | Recuperação e reprodutibilidade | 4 | `IN_PROGRESS` | Ensaios fechados repetidos alcançam ao menos 95% de êxito; tentativas são limitadas e falhas permitem retomada | [`runtime/providers/pje-recovery-state.v1.schema.json`](../../runtime/providers/pje-recovery-state.v1.schema.json), [`scripts/recover_pje_acquisition.py`](../../scripts/recover_pje_acquisition.py), [`scripts/acquire_pje_documents.py`](../../scripts/acquire_pje_documents.py) e `tests/test_pje_recovery.py`; nove testes sintéticos TRT99 comprovam checkpoints atômicos, limites imutáveis de tentativas, reuso de conteúdo aceito, subconjuntos explícitos, vínculo da requisição, custódia do catálogo e conteúdo local, validação semântica e esgotamento determinístico. Ainda faltam ensaios fechados TRT12 repetidos e autorizados e resultado empírico de 95% |

### 4.5 Capacidades do domínio trabalhista — 20 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| DOM-01 | Classificação documental trabalhista | 3 | `IN_PROGRESS` | Amostra aprovada atinge meta calibrada por tipo e preserva tipo desconhecido | [`runtime/domain/labor-document-classification.json`](../../runtime/domain/labor-document-classification.json), [`runtime/contracts/schemas/document-classification.v2.schema.json`](../../runtime/contracts/schemas/document-classification.v2.schema.json), [`scripts/classify_labor_documents.py`](../../scripts/classify_labor_documents.py), [`scripts/segment_pje_pdf.py`](../../scripts/segment_pje_pdf.py), [`scripts/migrate_document_classification_v1_to_v2.py`](../../scripts/migrate_document_classification_v1_to_v2.py) e testes de classificação, contratos, migração e linha do tempo. O contrato v1 aceito permanece imutável; v2 separa certidões e comunicações de decisões, com regras restritas a metadados e eventos neutros. Migração v1→v2 preserva tipos e desconhecidos sem inferir conteúdo; reclassificação exige regenerar artefatos dependentes. Ensaio apenas em memória do PDF TRT12 autorizado: 49 documentos, 46 classificados (93,9%), três desconhecidos e nenhum conflito; não houve materialização no repositório. O resultado de um processo não comprova acurácia nem conclui o pacote: ainda faltam revisão jurídica qualificada e calibração aprovada com vários processos |
| DOM-02 | Linha do tempo processual e relatório trabalhista | 3 | `IN_PROGRESS` | Datas, partes, fase, pedidos, defesas e localizadores passam na revisão cega da amostra | [`runtime/contracts/schemas/procedural-timeline.v1.schema.json`](../../runtime/contracts/schemas/procedural-timeline.v1.schema.json), [`runtime/contracts/schemas/labor-report.v1.schema.json`](../../runtime/contracts/schemas/labor-report.v1.schema.json), [`scripts/build_procedural_timeline.py`](../../scripts/build_procedural_timeline.py), [`scripts/build_labor_report.py`](../../scripts/build_labor_report.py), [`scripts/extract_labor_positions.py`](../../scripts/extract_labor_positions.py), [`scripts/extract_labor_defenses.py`](../../scripts/extract_labor_defenses.py), [`scripts/extract_pje_labor_report.py`](../../scripts/extract_pje_labor_report.py), `tests/test_procedural_timeline_builder.py`, `tests/test_labor_report_builder.py`, `tests/test_labor_position_extraction.py`, `tests/test_labor_defense_extraction.py` e `tests/test_pje_labor_report_extraction.py`; as suítes cobrem tipos documentais, localizadores, lacunas e conflitos, custódia exata de PDF/segmentos/classificação/linha do tempo, conciliação de partes, múltiplos reclamados e defesas, tribunal e grau portáveis, saída protegida, títulos de seção, quebras de linha, ordinais portugueses, IDs estáveis e CLIs. O processo TRT12 autorizado gerou relatório protegido válido conforme esquema com três partes vinculadas às fontes, fase de conhecimento do primeiro grau e unidade identificadas, 49 eventos datados, oito posições da parte autora e sete da defesa. Quatro categorias seguem `unmapped_`; a ausência de resposta específica sobre responsabilidade solidária/subsidiária permanece explícita. As lacunas globais por tipo de posição foram fechadas, mas o relatório v1 não afirma cobertura por pedido. Nada do processo foi versionado. Aceite depende de revisão jurídica cega em amostra TRT12 aprovada com vários processos |
| DOM-03 | Matriz de pedidos e providências requeridas | 4 | `IN_PROGRESS` | Sensibilidade mínima de 95% na calibração e cobertura de 100% dos pedidos na amostra final | [`runtime/domain/labor-claim-taxonomy.json`](../../runtime/domain/labor-claim-taxonomy.json), [`runtime/contracts/schemas/claim-matrix.v1.schema.json`](../../runtime/contracts/schemas/claim-matrix.v1.schema.json), [`scripts/build_claim_matrix.py`](../../scripts/build_claim_matrix.py), [`scripts/extract_labor_remedies.py`](../../scripts/extract_labor_remedies.py), [`scripts/extract_pje_claim_matrix.py`](../../scripts/extract_pje_claim_matrix.py), [`scripts/prepare_claim_blind_review.py`](../../scripts/prepare_claim_blind_review.py), `tests/test_claim_matrix_builder.py`, `tests/test_labor_remedy_extraction.py`, `tests/test_pje_claim_matrix_extraction.py` e `tests/test_claim_blind_review_packet.py`. Versão protegida de um processo preserva a matriz original e relaciona 16 entradas dos pedidos finais, inclusive oito subitens numerados, aos oito pedidos com evidência por página. As oito lacunas de providência ausente foram eliminadas. Restam quatro rótulos de pedidos não suportados, um conjunto de providências não suportado e um pedido sem defesa correspondente. A evidência protegida conserva duas alternativas condicionais e seis itens acessórios com letras não associados. Um formulário protegido e em branco foi preparado apenas com a fonte, sem ler saídas do sistema; nenhum revisor o concluiu ou congelou. Conteúdo processual não foi versionado. Aceite depende de revisão jurídica qualificada e calibração aprovada com vários processos; nenhum ponto foi concedido |
| DOM-04 | Matriz de provas | 4 | `IN_PROGRESS` | Cada alegação relevante aponta para a fonte; limitações e provas conflitantes são preservadas | [`runtime/contracts/schemas/evidence-matrix.v1.schema.json`](../../runtime/contracts/schemas/evidence-matrix.v1.schema.json), [`scripts/build_evidence_matrix.py`](../../scripts/build_evidence_matrix.py) e `tests/test_evidence_matrix_builder.py`; oito testes sintéticos cobrem montagem determinística, pedidos, contradições simétricas, limites do manifesto, rejeição de vínculos a si ou inexistentes, unicidade de IDs e coerência de estados controvertidos. Ainda falta revisão cega das alegações relevantes com amostra TRT12 aprovada |
| DOM-05 | Encaminhamento das questões por pedido | 3 | `IN_PROGRESS` | Cada pedido recebe trilha jurídica, probatória, de cálculos ou processual explicável, ou abstenção explícita | [`runtime/contracts/schemas/issue-route.v1.schema.json`](../../runtime/contracts/schemas/issue-route.v1.schema.json), [`scripts/build_issue_routes.py`](../../scripts/build_issue_routes.py) e `tests/test_issue_router.py`; oito testes sintéticos cobrem uma rota determinística por pedido, cobertura integral, abstenção explícita, exclusividade entre encaminhamento e abstenção, coerência de perguntas e rejeição de IDs duplicados ou desconhecidos. Ainda falta revisão cega das rotas com amostra TRT12 aprovada |
| DOM-06 | Análise dos pedidos, minuta e matriz do dispositivo | 3 | `IN_PROGRESS` | Todos os pedidos aceitos têm fatos, norma, fundamentação, resultado, limitações e vínculo ao dispositivo | [`runtime/contracts/schemas/claim-analysis.v1.schema.json`](../../runtime/contracts/schemas/claim-analysis.v1.schema.json), [`runtime/contracts/schemas/disposition-matrix.v1.schema.json`](../../runtime/contracts/schemas/disposition-matrix.v1.schema.json), [`scripts/build_claim_decisions.py`](../../scripts/build_claim_decisions.py) e `tests/test_claim_decision_builder.py`; oito testes sintéticos cobrem montagem determinística de análises, dispositivos e minuta, cobertura exata, custódia das provas, completude do resultado, limitações explícitas, IDs estáveis e duplicatas. Aceite depende de revisão jurídica cega da análise e minuta em amostra TRT12 aprovada |

### 4.6 Pesquisa em fontes de autoridade — 15 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| JUR-01 | Adaptador de fonte oficial do TST | 4 | `ACCEPTED` | Obtém resultado, estado, referência, URL e trecho literal oficiais nas consultas de teste | [`scripts/tst_official_adapter.py`](../../scripts/tst_official_adapter.py), `tests/test_tst_official_adapter.py` e [`runtime/providers`](../../runtime/providers); 12 testes sintéticos cobrem busca normalizada, filtro CNJ exato, paginação, corpus válido, custódia literal, restrições de fonte e origem, limites de resposta e variantes de data. Consulta real delimitada em 2026-09-21 obteve o documento TST `7a2d741d22e82084a45f85ba428fa103` do serviço HTTPS oficial, gerando fonte válida e preservando estado `unknown` para revisão humana |
| JUR-02 | Adaptador de jurisprudência do TRT12 | 4 | `IN_REVIEW` | Cobre fontes TRT12 aprovadas e distingue material PJe atual da cobertura legada | [`scripts/trt12_official_adapter.py`](../../scripts/trt12_official_adapter.py), `tests/test_trt12_official_adapter.py` e [`runtime/providers`](../../runtime/providers); testes sintéticos cobrem busca conjunta de sentenças/acórdãos, escopo TRT12, paginação iniciada em zero, URLs permanentes por coleção, detalhes, custódia literal, cobertura atual/legada, corpus válido, interface compartilhada, formatos por endpoint, limites e rejeição de registros ambíguos. O portal oficial remete a pesquisa PJe atual ao Falcão para primeiro e segundo graus desde 2016. Duas tentativas delimitadas em 2026-09-21 pararam no limite oficial antes da busca. Em 2026-09-24, nova tentativa única abriu a sessão, mas a busca retornou HTTP 403; não houve repetição. Ainda falta conferir custódia real de sentença e acórdão |
| JUR-03 | Adaptador de precedentes do TRT12 | 3 | `ACCEPTED` | Registra estado, âmbito, suspensão e fonte oficial de IRDR/IAC/teses regionais | [`scripts/trt12_precedent_adapter.py`](../../scripts/trt12_precedent_adapter.py), `tests/test_trt12_precedent_adapter.py` e [`runtime/providers`](../../runtime/providers); 11 testes sem rede cobrem estados de IRDR, suspensão ativa no segundo grau, paginação limitada, cabeçalho Google Visualization, teses IUJ vigentes/canceladas, ausência explícita de tese IAC sem fabricar precedente, interface comum, URLs restritas, limite de resposta e corpus válido. Consultas reais delimitadas em 2026-09-21 obtiveram Tema IRDR 34 suspenso no segundo grau, ausência oficial de tese IAC e Tese IUJ 3 vigente das publicações TRT12 |
| JUR-04 | Consolidação de precedentes e custódia das citações | 4 | `ACCEPTED` | Deduplicação, hierarquia, conflitos de estado e fidelidade das citações passam em casos determinísticos | [`scripts/consolidate_precedents.py`](../../scripts/consolidate_precedents.py), `tests/test_precedent_consolidation.py` e [`runtime/providers`](../../runtime/providers); 11 testes cobrem hierarquia, duplicatas, IDs repetidos conflitantes, fontes equivalentes, apelidos, conflitos de estado, precedência de estado desconhecido, citações, relatório auxiliar determinístico, contratos inválidos e corpus consolidado válido. Cada fonte original conserva URL oficial e resumo SHA-256 do trecho no relatório auxiliar |

### 4.7 Pipeline e verificações de ponta a ponta — 15 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| PIP-01 | Orquestrador retomável do primeiro grau para Claude Code e Codex | 3 | `ACCEPTED` | Nos dois ambientes, execução interrompida retoma sem repetir etapas aceitas nem confiar em etapas vencidas | [`scripts/resumable_pipeline.py`](../../scripts/resumable_pipeline.py), [`runtime/pipelines/execution-state.v1.schema.json`](../../runtime/pipelines/execution-state.v1.schema.json), `tests/test_resumable_pipeline.py` e [`runtime`](../../runtime); dez testes determinísticos cobrem retomada, reuso entre ambientes com despacho próprio, atualização de saídas/dependências, revalidação de controles, invalidação de fontes/contratos, ordem, limites de tentativa, saídas obrigatórias, gravação atômica e estado neutro válido. Não há capacidade de ação externa |
| PIP-02 | Trilhas condicionais por pedido | 3 | `ACCEPTED` | Pesquisa, prova, cálculo e revisão processual só executam quando encaminhados; abstenção é válida | [`scripts/build_conditional_work_plan.py`](../../scripts/build_conditional_work_plan.py), [`runtime/pipelines/conditional-work-plan.v1.schema.json`](../../runtime/pipelines/conditional-work-plan.v1.schema.json) e `tests/test_conditional_work_plan.py`; 11 testes cobrem despacho por pedido, abstenção sem despacho, cenários mistos, ordem/IDs estáveis, coerência da rota, limites de perguntas e motivos, duplicatas, contratos inválidos, esquema válido e rejeição de pedido encaminhado sem tarefa |
| PIP-03 | Controles de congruência entre pedido, fundamentação e dispositivo | 4 | `ACCEPTED` | Pedido ausente e dispositivo órfão falham; amostra de aceite atinge cobertura de 100% | [`scripts/validate_decision_congruence.py`](../../scripts/validate_decision_congruence.py), [`runtime/pipelines/decision-congruence-report.v1.schema.json`](../../runtime/pipelines/decision-congruence-report.v1.schema.json) e `tests/test_decision_congruence.py`; 14 testes comprovam cobertura exata de análise, dispositivo e minuta e bloqueiam ausência, duplicata, ID desconhecido, divergência, fundamentação vazia, fonte inválida, resultado, título e esquema divergentes |
| PIP-04 | Controles de citações, fontes, cálculos e aceite final | 3 | `ACCEPTED` | Citações sem suporte e critérios incoerentes bloqueiam; indisponibilidade de fonte é explícita | [`scripts/evaluate_final_gate.py`](../../scripts/evaluate_final_gate.py), [`runtime/pipelines/final-review.v1.schema.json`](../../runtime/pipelines/final-review.v1.schema.json), [`runtime/pipelines/global-gate.v1.schema.json`](../../runtime/pipelines/global-gate.v1.schema.json) e `tests/test_final_acceptance_gate.py`; 13 testes cobrem citações, limite de citação curta, fontes ausentes/indisponíveis, concordância exata de critérios, cálculos dispensados/indisponíveis, revisões duplicadas, falha anterior, relatório válido e bloqueio obrigatório. Indisponibilidade gera relatório `blocked` com objeto e motivo, não aceite silencioso |
| PIP-05 | Ensaio sintético/sanitizado de ponta a ponta nos dois ambientes | 2 | `ACCEPTED` | Os adaptadores de Claude Code e Codex materializam os artefatos e o controle global aprovado em espaços limpos | [`scripts/run_synthetic_pipeline.py`](../../scripts/run_synthetic_pipeline.py), `tests/fixtures/pipeline/synthetic-first-instance.json` e `tests/test_cross_runtime_pipeline.py`; o ensaio automatizado atual gera 24 saídas obrigatórias, com entrada, narrativa e triagem congeladas verificadas antes da escrita. Testes de subprocesso comprovam igualdade dos artefatos compartilhados, controle global, proteção do espaço, bloqueio de divergência entre relatório e matriz, rejeição de narrativa com resumo antigo e incompatibilidade entre triagem herdada e rota derivada. Os dados são sintéticos e esse ensaio automatizado não invoca agentes de modelo; isso não prova PJe real nem adequação jurídica |

### Ponto de controle da convergência com o fluxo herdado (sem pontuação)

O ensaio automatizado do pipeline comprova contratos e verificações compartilhados;
o ensaio local adicional comprova o despacho dos agentes apenas com dados sintéticos.
Este ponto evita confundir um
segundo fluxo com a adaptação do fork. Não rende pontos adicionais até que um
critério de aceite já pontuado seja atendido. O [mapa de convergência](../inventory/superjurista-flow-convergence.md)
registra cada etapa herdada e seu tratamento no TRT12.

- [x] Uma entrada protegida e sem sobrescrita apresenta o relatório e a matriz
  existentes ao triador herdado, rejeitando divergências de origem entre pedidos e defesas.
- [x] A variante TRT12 do triador não usa ferramentas de pesquisa da Justiça
  Federal; um importador determinístico confere a rota C2 herdada, cada rota
  por pedido, a política de fontes e a saída sem sobrescrita em casos sintéticos.
- [x] A etapa compartilhada `route-claims` vincula as instruções do triador
  adaptado para Claude Code e Codex, inclusive seu resumo criptográfico; o
  planejamento de retomada informa o agente vinculado.
- [x] Uma entrada protegida do processo autorizado com oito pedidos foi
  preparada localmente; antes de aceitar a rota, o importador exige a entrada
  atual exata e seu resumo repetido pelo agente. Nenhuma saída de modelo foi
  aceita naquele processo real.
- [x] A variante trabalhista do relator herdado preserva a narração
  cronológica, mas trata `labor-report.json` como referência e não como saída
  concorrente; as regras previdenciárias não passam ao perfil TRT12.
- [x] Um validador sintético confere custódia da entrada e cobertura exata de
  eventos, pedidos e defesas na narrativa do relator, além do formato herdado. Isso não
  comprova que o agente tenha sido executado nem a correção jurídica do texto.
- [x] O manifesto vincula `prepare-triage-input` e `narrate-record` antes da
  triagem. O ensaio entre ambientes valida uma narrativa congelada e bloqueia
  relatório/matriz divergentes ou resumo de entrada desatualizado sem escrever
  saídas. Continua sendo execução determinística, sem despacho de modelo.
- [x] O checkpoint sintético aceita entrada, narrativa e triagem usando
  controle de conteúdo real; vínculos simbólicos em saídas ou insumos e rotas
  divergentes do documento herdado são recusados. O validador específico recusa
  outras etapas, ainda sem afirmar despacho do pipeline completo.
- [x] O despacho opt-in do relator no Codex usa insumos coerentes, sandbox de
  leitura e publicação sem sobrescrita somente após validar a narrativa.
  Testes com resposta controlada cobrem aceite e falhas; nenhum modelo foi
  executado por esse teste, então não há pontos adicionais de aceite.
- [x] O despacho opt-in do triador no Codex exige a narrativa aceita,
  valida o Markdown C2 herdado, gera as fontes vazias e deriva a rota por
  pedido sem aceitar saídas parciais ou sobrescrita. Os testes substituem a
  execução externa; nenhuma triagem foi produzida pelo modelo nesses testes e
  não há pontos adicionais de aceite.
- [x] O primeiro checkpoint do manifesto completo (`prepare-profile`) usa
  validação de conteúdo TRT12 e do plano resolvido, com retomada sintética.
  Os controles posteriores continuam sujeitos às próprias evidências; nenhum
  ponto foi alterado.
- [x] `acquire-case` aceita um checkpoint sintético somente com índice PJe
  completo, estado de recuperação do fork, escopo autorizado confrontado
  externamente e bytes locais com tamanho e SHA-256 íntegros. O manifesto
  curto do ensaio anterior é recusado; PJe real e autorização jurídica não
  foram comprovados, sem novos pontos de aceite.
- [x] `extract-record` aceita o terceiro checkpoint sintético somente quando
  aquisição, classificação, linha do tempo e relatório cobrem os mesmos
  documentos com contexto e fontes coerentes. Aquisição parcial, motivo de
  classificação incoerente e relatório defasado são recusados. A retomada
  aponta para `build-decision-units`; não há novos pontos de aceite nem prova
  de extração ou interpretação jurídica em autos reais.
- [x] `build-decision-units` aceita o quarto checkpoint sintético somente com
  cobertura exata das posições do relatório, remédios e lacunas coerentes com
  o construtor herdado, referências documentais conhecidas e matriz de provas
  vinculada aos pedidos. O validador composto recusa etapas não implementadas,
  aceita a entrada protegida do triador no quinto checkpoint e aponta para
  `narrate-record`. Isso não atesta veracidade
  probatória ou revisão jurídica, portanto não altera os pontos de aceite.
- [x] Em 24/09/2026, um ensaio local executou de fato relator e triador Codex
  sobre a amostra sintética protegida, aceitou suas saídas pelos validadores e
  retomou sete checkpoints consecutivos no manifesto completo. A próxima
  etapa é `execute-conditional-tracks`. Não houve PJe real, conclusão jurídica
  nem revisão qualificada; a pontuação de aceite permanece inalterada.
- [x] `execute-conditional-tracks` exige recibo por trabalho `WRK-*`, fontes
  vinculadas ao pedido, estados explícitos de prova e cálculo e ausência de
  saídas para trilhas desabilitadas. Uma abstenção integral gera passagem sem
  trabalho fictício. O ensaio sintético registra e invalida o oitavo
  checkpoint quando o recibo muda; a próxima etapa é `analyze-claims`.
  A pesquisa e as revisões continuam sem certificação jurídica, sem novos
  pontos de aceite.
- [x] `analyze-claims` cruza cada análise com pedido, rota, fontes e estados
  de revisão. A amostra sintética não afirma fatos enquanto a prova está
  pendente; conclusões de mérito sem revisão e referências órfãs são
  recusadas. O ensaio registra o nono checkpoint e invalida sua retomada
  quando a análise muda. A próxima etapa é `draft-judgment`. Este é um
  controle técnico, não aceite jurídico de `DOM-06`; a pontuação permanece
  inalterada.
- [x] O analisador herdado adaptado recebeu os insumos atuais da etapa
  documental fictícia em execução efetiva do Codex CLI; um recibo local vincula
  fontes, instruções e resposta aceita. A revisão humana continua pendente.
- [x] O fundamentador herdado adaptado recebeu a análise documental fictícia
  atual na mesma execução encadeada e publicou apenas dispositivo sem comando
  e minuta para revisão. O controle `draft-congruence` aceitou o décimo
  checkpoint; não houve revisão jurídica ou novo ponto de aceite.
- [x] `draft-judgment` reutiliza o construtor herdado da minuta e o validador
  de congruência entre pedido, análise e dispositivo. Resultado pendente ou
  abstido não pode trazer comando operativo, efeitos ou critérios de cálculo.
  A variante TRT12 do fundamentador está vinculada à etapa para produzir
  somente a matriz do dispositivo; a redação final permanece determinística.
  `run_draft_judgment_stage.py` exige a etapa atual e publica os dois arquivos
  privados sem sobrescrita, revertendo ambos se o controle os recusar.
  A minuta deve corresponder à renderização determinística; uma frase extra
  de procedência fez o ensaio anterior falhar no teste de regressão. O décimo
  checkpoint é retomável e se invalida quando a minuta muda; a próxima etapa
  é `merge-judgment`. A revisão jurídica de `DOM-06` continua pendente e a
  pontuação de aceite não aumenta.
- [x] `merge-judgment` exige igualdade literal entre a minuta aceita e o
  arquivo por processo, sem acréscimos nem vínculos simbólicos. O ensaio
  alcança o décimo primeiro checkpoint e invalida a fusão quando o arquivo
  muda. `run_merge_judgment_stage.py` agora publica exatamente os bytes da
  minuta aceita, com acesso privado e sem sobrescrita, somente quando esta
  etapa é a próxima do manifesto. A próxima etapa é `review-and-gate`; o relatório técnico atual ainda
  não deve ser interpretado como aprovação jurídica de um pedido pendente.
  Nenhum ponto adicional de aceite foi concedido.
- [x] `review-and-gate` recalcula o relatório final e confere fontes e
  cálculos com seus artefatos de origem. O ensaio com
  `pending_human_review` permanece no décimo primeiro checkpoint apesar
  do `passed` técnico anterior; uma variação de abstenção explícita percorre
  os doze checkpoints sem comando dispositivo. Isso mede a execução do
  grafo, não aprovação jurídica nem prontidão para emissão de sentença.
  A pontuação de aceite permanece inalterada.
- [ ] Uma narrativa produzida a partir de autos TRT12 autorizados, e não apenas
  da amostra sintética, passa na validação antes da triagem.
- [ ] O relator herdado e o triador adaptado são executados e revisados no
  processo TRT12 autorizado; o ensaio sintético não comprova adequação jurídica.
- [ ] As saídas produzidas pelos agentes passam nos contratos do relatório e
  das rotas por pedido, preservam cada pedido e referência à fonte e não criam
  uma leitura jurídica concorrente.
- [ ] Um ensaio controlado com processo TRT12 e revisão jurídica qualificada
  comprovam adequação semântica; testes sintéticos não satisfazem essa condição.

### 4.8 Validação histórica — 10 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| VAL-01 | Protocolo congelado de validação histórica | 2 | `ACCEPTED` | Amostragem, categorias, formulário, gravidade e plano são fixados antes de observar resultados | [`runtime/validation/historical-validation-protocol.v1.json`](../../runtime/validation/historical-validation-protocol.v1.json), [`runtime/validation/historical-validation-protocol.v1.schema.json`](../../runtime/validation/historical-validation-protocol.v1.schema.json), [`spec/validation/historical-blind-review-form.md`](../validation/historical-blind-review-form.md), [`scripts/validate_historical_protocol.py`](../../scripts/validate_historical_protocol.py) e `tests/test_historical_validation_protocol.py`; nove testes congelam método para 20 processos autorizados, 15 de desenvolvimento e cinco de reserva intocada, categorias, pontuação e arbitragem cegas, formulário, tolerância zero a defeitos críticos/altos, sensibilidade de 95%, cobertura de 100%, suporte de citações e rastreabilidade, rejeitando resultados ou metas definidos depois |
| VAL-02 | Revisão histórica cega | 4 | `IN_PROGRESS` | Amostra aprovada de 15 processos de desenvolvimento concluída, com defeitos rastreáveis por etapa e gravidade | [`runtime/validation`](../../runtime/validation), [`scripts/score_historical_reviews.py`](../../scripts/score_historical_reviews.py), [`spec/validation/historical-blind-review-form.md`](../validation/historical-blind-review-form.md) e `tests/test_historical_review_scoring.py`; testes determinísticos exigem fase de 15 casos antes da reserva separada de cinco, inventários congelados, vínculo a protocolo/revisão/categoria, atestados cegos, motivos de indisponibilidade sem presumir aprovação, saída válida, custódia pseudonimizada de defeitos e reprovação automática por defeitos críticos/altos. Ainda faltam revisão de desenvolvimento autorizada e revisor qualificado identificado |
| VAL-03 | Correção e nova execução na reserva intocada | 2 | `IN_PROGRESS` | Defeitos críticos/altos são corrigidos; cinco processos separados passam sem regressão | [`runtime/validation/historical-correction-register.v1.schema.json`](../../runtime/validation/historical-correction-register.v1.schema.json), [`runtime/validation/historical-rerun-report.v1.schema.json`](../../runtime/validation/historical-rerun-report.v1.schema.json), [`scripts/validate_historical_rerun.py`](../../scripts/validate_historical_rerun.py) e `tests/test_historical_rerun.py`; oito testes vinculam evidência à revisão de base, exigem regressões aprovadas para defeitos materiais, preservam IDs/gravidade/etapa/código, rejeitam promoção de métricas adulteradas, exigem revisão corrigida distinta e só aceitam reserva separada de cinco casos aprovada no protocolo. Ainda faltam resultados reais, correções e evidência da reserva |
| VAL-04 | Dossiê de aceite | 2 | `IN_PROGRESS` | Resultados, limites, modos de falha e recomendação de seguir/não seguir são aprovados | [`runtime/validation/historical-dossier-review.v1.schema.json`](../../runtime/validation/historical-dossier-review.v1.schema.json), [`runtime/validation/historical-acceptance-dossier.v1.schema.json`](../../runtime/validation/historical-acceptance-dossier.v1.schema.json), [`scripts/build_historical_acceptance_dossier.py`](../../scripts/build_historical_acceptance_dossier.py) e `tests/test_historical_acceptance_dossier.py`; sete testes vinculam desenvolvimento, reserva e correções ao protocolo e às revisões exatas, separam resultados, exigem limitações e falhas, rejeitam divergência de fontes e defeitos materiais, impõem identidade de decisão pendente/aprovada/rejeitada e impedem promoção de rejeição ou `no_go`. Mesmo aprovado, o dossiê permite apenas trabalho local supervisionado, sem atos judiciais externos. Faltam resultados reais e aprovação humana final |

### 4.9 Preparação do piloto controlado — 2 pontos

| ID | Entrega | Pontos | Situação | Critério de aceite | Evidências |
|---|---|---:|---|---|---|
| OPS-01 | Manual de instalação e operação | 1 | `ACCEPTED` | Ensaio limpo do operador conclui apenas com o manual | [`spec/operations/trt12-first-instance-operator-runbook.md`](../operations/trt12-first-instance-operator-runbook.md), [`scripts/rehearse_target_host.py`](../../scripts/rehearse_target_host.py) e [`scripts/run_synthetic_pipeline.py`](../../scripts/run_synthetic_pipeline.py); clone remoto limpo de `development` no commit `fda75cd` criou ambiente Python 3.12.14 e instalou as dependências de runtime e dos cinco servidores MCP. O ensaio do host retornou `ready`, cinco servidores, uma página OCR e resumo `f925340cc3be04b5ef1dffe47ac317a64e0ec452eb6688f5350dc571647f1515`. O controle completo passou 751 testes; 12 testes entre ambientes passaram. O executor sintético configurado para Claude Code e Codex gerou 24 artefatos por ambiente, com controle global da amostra aprovado, resumo de contrato `8bc0f992871b3afaf71a2cb13af314ebbf1fbef49580bfa275462052be37a07e` e resumo compartilhado `ea9dfcfef3c132eef1a8ea0404e5d41eb2be1a2140b8f4ce012153553cf4ee67` idênticos; os relatórios examinados tinham permissão `0600`. Não houve despacho do agente Claude, autos reais ou revisão jurídica |
| OPS-02 | Plano de segurança e reversão do piloto | 1 | `ACCEPTED` | Revisão humana, incidentes, reversão, retenção e responsáveis aprovados | [`spec/operations/pilot-safety-rollback-plan.md`](../operations/pilot-safety-rollback-plan.md), [`runtime/operations/pilot-preflight.v4.schema.json`](../../runtime/operations/pilot-preflight.v4.schema.json), [`scripts/validate_pilot_preflight.py`](../../scripts/validate_pilot_preflight.py) e `tests/test_pilot_preflight.py`; usuário aprovou titular do repositório como operador, responsável por incidentes e dados, exigiu revisor jurídico qualificado por processo e prazos máximos de 24 horas para HAR bruto, 30 dias após revisão para documentos, 90 dias para derivados e 180 dias para resumos operacionais sem segredos. Os testes impõem `NO-GO` por processo até aprovação de autorização, ausência de sigilo, revisor, commit limpo, host e qualidade, resumos Claude/Codex idênticos e vinculados ao manifesto vigente, mapa revisado, número TRT12 protegido, validade temporal, provedor de modelo autorizado, caminhos externos ao repositório, saída vazia e retenção limitada. Prazo HAR conta da captura; falhas não observadas ficam explícitas sem provocá-las; atos judiciais externos permanecem desabilitados |

---

## 5. Marcos da frente A

| Marco | Itens que precisam estar aceitos | Resultado |
|---|---|---|
| M0 — base reutilizável segura | FND-01 a FND-04 | O valor herdado foi caracterizado e o repositório sustenta implementação incremental confiável |
| M1 — contratos definidos | ARC-01 a ARC-04 | A separação entre núcleo e perfil é executável e versionada |
| M2 — obtenção autorizada | PJE-01 a PJE-05 | Autos do primeiro grau do TRT12 podem ser obtidos de modo reprodutível |
| M3 — processo estruturado | DOM-01 a DOM-05 | Pedidos, defesas, evidências e rotas tornam-se rastreáveis |
| M4 — pesquisa em fontes oficiais | JUR-01 a JUR-04 | O conjunto pesquisado é oficial, hierarquizado e auditável |
| M5 — pipeline completo de minuta | DOM-06 e PIP-01 a PIP-05 | A minuta e todas as verificações executam de ponta a ponta |
| M6 — validação histórica | VAL-01 a VAL-04 | A qualidade é medida em evidências históricas congeladas |
| M7 — candidato a piloto | OPS-01 e OPS-02 | Um piloto controlado, supervisionado por pessoas, pode ser considerado |

Os marcos são condições de dependência, não datas. Datas serão acrescentadas
quando a capacidade de implementação e o acesso aos casos TRT12 forem conhecidos.

---

## 6. Frente B — segundo grau do TRT12

A frente B começa somente após o marco M5 da frente A, salvo se uma dependência
arquitetural explícita precisar ser resolvida antes.

| Pacote de trabalho | Peso | Resultado para aceite |
|---|---:|---|
| B-ARC — contratos e escopo recursal | 10 | Contratos versionados para capítulos recorridos e dispositivo recursal |
| B-PJE — obtenção de dados do segundo grau | 20 | Adaptador PJe do segundo grau verificado |
| B-DOM — análise de recursos e redação de voto | 30 | Artefatos de admissibilidade, efeito devolutivo, resultado por capítulo e voto |
| B-JUR — pesquisa por órgão julgador e divergência | 10 | Metadados regionais e tratamento da autoridade dos precedentes |
| B-PIP — orquestração e verificações do segundo grau | 15 | Pipeline retomável de voto com verificações de congruência recursal |
| B-VAL — validação histórica cega | 12 | Protocolo congelado, revisão, correção e nova execução em amostra intocada |
| B-OPS — preparação do piloto controlado | 3 | Guia operacional e aprovação de piloto supervisionado por pessoas |
| **Total** | **100** |  |

A frente B permanece em zero até que seus itens sejam decompostos em tarefas
com evidências e aceitos.

---

## 7. Frente C — portabilidade para outros TRTs

A frente C começa com a seleção deliberada de um segundo TRT, não pela
duplicação dos arquivos do TRT12.

| Pacote de trabalho | Peso | Resultado para aceite |
|---|---:|---|
| C-ABS — verificar diferenças reais e ajustar interfaces | 10 | As diferenças são demonstradas, não presumidas |
| C-PRO — perfil do segundo TRT | 20 | Perfil válido e política local definida |
| C-PJE — adaptador PJe do segundo TRT ou prova de compartilhamento | 25 | A obtenção de dados passa em ensaios específicos do tribunal |
| C-JUR — adaptador de pesquisa do segundo TRT | 20 | Precedentes e jurisprudência regionais verificados |
| C-REG — regressão entre TRTs | 20 | O TRT12 continua passando enquanto o segundo TRT também passa |
| C-OPS — guia de portabilidade | 5 | Um terceiro perfil pode seguir processo documentado |
| **Total** | **100** |  |

O projeto só poderá se apresentar como validado para mais de um TRT depois que
a frente C alcançar 100 pontos.

---

## 8. Indicadores de qualidade

Os pontos de avanço respondem «quanta capacidade foi aceita?». Os indicadores
de qualidade respondem «ela é confiável o suficiente para avançar?».

### 8.1 Indicadores principais

| Indicador | Definição | Meta | Decisão apoiada |
|---|---|---:|---|
| Avanço de capacidade aceita | Pontos aceitos da frente A divididos por 100 | 100% no produto mínimo | Preparação da entrega |
| Taxa de execuções aceitas de ponta a ponta | Execuções que passam em todas as verificações obrigatórias / execuções elegíveis | Calibrar; depois, pelo menos 95% | Confiabilidade operacional |
| Taxa de defeitos jurídicos críticos | Defeitos críticos / processos revisados às cegas | 0 antes do piloto | Iniciar ou não iniciar |

### 8.2 Indicadores de diagnóstico

| Indicador | Definição | Uso |
|---|---|---|
| Recuperação de pedidos | Pedidos da referência encontrados / pedidos da referência | Diagnosticar omissões |
| Cobertura de congruência | Pedidos com fundamentação e dispositivo / pedidos mapeados | Diagnosticar integridade estrutural |
| Rastreabilidade de citações | Citações externas verificadas / citações externas | Diagnosticar a disciplina de fontes |
| Falhas explícitas dos adaptadores | Falhas registradas explicitamente / operações com falha | Detectar falhas silenciosas |
| Encerramento de regressões | Defeitos aceitos e encerrados / defeitos aceitos encontrados | Medir o aprendizado com falhas |
| Cobertura de classificação do fork | Componentes abrangidos com tratamento fundamentado / componentes abrangidos | Evitar reescritas acidentais e dependências herdadas invisíveis |
| Reuso realizado | Componentes preservados ou adaptados e aceitos / componentes inicialmente elegíveis | Mostrar quanto do fork foi aproveitado no TRT12 |
| Conformidade entre ambientes | Casos compartilhados que passam em ambos os ambientes / casos compartilhados elegíveis | Detectar divergência sem exigir prosa idêntica |

### 8.3 Limites de segurança

| Limite | Valor permitido |
|---|---|
| Citação externa sem suporte | Zero |
| Item de dispositivo sem pedido correspondente | Zero |
| Pedido omitido sem aviso | Zero na amostra de aceite |
| Vazamento de credenciais ou dados sigilosos em logs/casos sintéticos | Zero |
| Protocolo, assinatura ou publicação externa | Zero no produto mínimo |
| Item de avanço sem evidência vinculada | Não pode ficar `ACCEPTED` |
| Regra jurídica ou contrato de artefato específico do ambiente | Zero; diferenças devem ficar apenas nos adaptadores de execução |

Metas dependentes da distribuição empírica continuam provisórias até a
calibração. Podem ser endurecidas após a linha de base, mas não flexibilizadas
apenas para declarar um marco concluído.

---

## 9. Ritmo de revisão

Atualize este roteiro a cada solicitação de alteração aceita ou marco equivalente
de entrega.

### Revisão semanal ou por marco

1. Recalcular os pontos aceitos.
2. Verificar se cada item aceito ainda possui evidências válidas.
3. Relacionar novos defeitos críticos ou graves.
4. Identificar o próximo item de maior valor sem bloqueio.
5. Registrar bloqueios, responsáveis e decisões necessárias.
6. Atualizar indicadores apenas com evidências reproduzíveis.

### Modelo de informe de situação

```text
Data:
Avanço da frente A: X/100
Avanço do programa: Y%
Marco alcançado:
Itens aceitos no período:
Evidências:
Itens reabertos:
Defeitos críticos/graves:
Bloqueio atual:
Próximo alvo de aceite:
```

---

## 10. Registro de decisões

| Data | Decisão | Efeito |
|---|---|---|
| 2026-09-20 | O primeiro grau do TRT12 é o primeiro alvo executável | Trilha A criada |
| 2026-09-20 | O segundo grau do TRT12 terá um fluxo futuro separado | Trilha B criada |
| 2026-09-20 | Outros TRTs exigem comprovação de portabilidade | Trilha C criada |
| 2026-09-20 | Somente evidências aceitas geram pontos de progresso | Adotada pontuação binária ponderada por evidências |
| 2026-09-20 | O fork é a base da implementação, não um protótipo descartável | Adotadas migração com prioridade ao reuso e `FND-04` |
| 2026-09-20 | Claude Code e Codex são ambientes principais sobre um núcleo compartilhado | Contratos dos dois ambientes adicionados à Trilha A |
| 2026-09-20 | Scripts centrais aceitam Python 3.9+; servidores MCP locais exigem Python 3.10+ e SDK MCP 1.x | Contrato de executáveis e dependências incluído em `FND-01` |
| 2026-09-20 | Desenvolvimento local e CI compartilham um comando determinístico de qualidade | Fluxo para Python 3.9/3.10 e controles de bloqueio seguro incluídos em `FND-02` |
| 2026-09-20 | Arquivos locais sensíveis permanecem ignorados; arquivos rastreados e preparados para commit são examinados sem exibir valores | Contrato executável de higiene incluído em `FND-03` |
| 2026-09-21 | Estrutura de tribunais, registro de provedores e valores do TRT12 são contratos versionados separados | `ARC-02` permanece portável, com primeiro grau ativo e segundo grau desabilitado |
| 2026-09-21 | Esquemas dos artefatos jurídicos usam catálogo versionado e migrações explícitas com bloqueio seguro | Contratos `ARC-03` compartilhados por Claude Code e Codex sem constantes de tribunal |
| 2026-09-21 | Provedores de PJe e pesquisa implementam contratos versionados por capacidade | `ARC-04` valida provedores simulados do TRT99 sem constantes do TRT12 no núcleo |
| 2026-09-21 | HARs brutos e sessões ficam locais; mapas sanitizados e revisados podem servir como evidência | `PJE-01` mapeia endpoints sem reter credenciais, valores de consulta, corpos ou identificadores dinâmicos |
| 2026-09-21 | Mapas HAR sanitizados exigem controle separado de integridade e cobertura antes da revisão humana | Observações ausentes ficam explícitas; adulteração ou divergência do alvo bloqueia o fluxo |
| 2026-09-21 | Classificação da sessão é separada da obtenção de credenciais | `PJE-02` valida observações sintéticas sem segredos; verificação real do TRT12 ainda depende de evidência `PJE-01` |
| 2026-09-21 | Descoberta de tarefas e processos usa páginas normalizadas e limitadas | `PJE-03` detecta perda silenciosa na paginação sem assumir endpoints, tarefas ou campos do TRF5 como fatos do TRT12 |
| 2026-09-21 | Triagem documental trabalhista usa regras determinísticas versionadas e preserva incertezas | `DOM-01` avança com dados sintéticos sem copiar os autos nem alegar acurácia calibrada para TRT12 |
| 2026-09-21 | Relatórios processuais são estruturados, vinculados às fontes e preservam lacunas explícitas | `DOM-02` avança sinteticamente; calibração com processo real continua sendo critério separado |
| 2026-09-21 | Matrizes de pedidos preservam defesas múltiplas vinculadas às fontes e não ocultam lacunas da taxonomia | `DOM-03` avança sinteticamente sem alegar sensibilidade ou cobertura final antes da revisão real |
| 2026-09-22 | Matriz protegida exige associação explícita entre documento de defesa e reclamado, preservando providências ausentes e pedidos sem resposta | `DOM-03` tem artefato parcial de um processo, sem alegar sensibilidade calibrada nem cobertura final |
| 2026-09-22 | Extração dos pedidos finais conserva página, pedidos alternativos e acessórios não associados, sem sobrescrever a matriz protegida anterior | `DOM-03` reduz de oito a zero as lacunas de providências em um processo; permanecem revisão de taxonomia e defesas ausentes, sem calibração concluída |
| 2026-09-23 | Revisão independente começa pelo PDF custodiado e formulário protegido em branco, sem previsões do sistema | Instrumento de revisão pronto; não se alega inventário humano, arbitragem, medição de sensibilidade nem aceite de `DOM-03` |
| 2026-09-23 | Convergir contratos do TRT12 com o fluxo herdado de agentes antes de ampliar extração paralela ou buscar aceite jurídico | Entrada protegida da triagem vinculada às fontes, variante TRT12 e importador C2 por pedido implementados; execução do agente herdado e adequação jurídica não verificadas, sem alteração dos pontos aceitos |
| 2026-09-24 | A verificação prévia do piloto deve rejeitar resumos sintéticos de contrato anterior, mesmo quando Claude Code e Codex concordam entre si | Contrato v2 compara contagem de saídas e resumo do manifesto vigente; o ensaio atual produz 24 artefatos. O processo real continua sem revisão jurídica independente e sem autorização de piloto `GO` |
| 2026-09-24 | Despachar as variantes herdadas do relator e do triador pelo Codex em um caso sintético, além de verificar saídas congeladas | Narrativa, triagem e rota por pedido geradas pelo modelo passaram nos três checkpoints de transferência; execução no Claude Code e adequação jurídica do processo real permanecem sem evidência, sem novos pontos de aceite |
| 2026-09-24 | Exercitar o relator e o triador com oito pedidos sintéticos e uma defesa ausente | Todos os oito IDs foram preservados; sete rotas probatórias e uma abstenção explícita passaram nos três checkpoints. A escala dos autos reais, a revisão jurídica e o Claude Code ainda não foram validados; nenhum novo ponto foi concedido |
| 2026-09-24 | Impedir que comandos diretos do Codex enviem autos arbitrários ao modelo sem autorização de piloto | Relator e triador recusam despacho por padrão; o modo de ensaio compara os insumos com a amostra sintética versionada antes de chamar o Codex. O despachante real condicionado ao `GO` específico foi implementado depois, mas ainda não foi executado com autos reais; nenhum ponto jurídico foi concedido |
| 2026-09-24 | Tornar repetível o ensaio direto dos agentes sem copiar material processual | Preparador cria apenas relatório, matriz e entrada da amostra sintética num diretório externo, vazio e privado; os despachantes exigem essa identidade antes de chamar o modelo. O caminho de caso real permanece pendente |
| 2026-09-24 | Vincular a preparação de insumos reais ao `GO` vigente e ao mesmo processo autorizado | Verificação prévia v3 acrescenta número CNJ protegido e vencimento; preparador de piloto recusa divergência entre autorização, relatório, matriz e entrada, exige diretórios privados e cria apenas três arquivos `0600`. Naquele ponto não havia chamada ao modelo nem aceite jurídico |
| 2026-09-24 | Condicionar o despacho real do Codex ao provedor autorizado e aos controles herdados | Contrato v4 requer provedor explícito; orquestrador encadeia relator e triador após GO, revalida prazo, checkout e integridade antes e depois de cada chamada, aplica os três controles de transferência e preserva saídas parciais. Testes usam respostas simuladas; não há evidência de execução em processo real nem revisão jurídica, sem novos pontos de aceite |
| 2026-09-24 | Tornar auditável o ensaio do piloto sem expor os autos | Registro protegido fixa `codex_model_id`, despachos usam `--model`, e `pilot-run-summary.json` guarda hashes de insumos e saídas com estado `pending_legal_review`; sobrescrita é recusada. Testes exercitam respostas simuladas, não uma execução jurídica real; avanço ponderado permanece inalterado |
| 2026-09-24 | Conferir independentemente o conjunto do piloto antes da revisão jurídica | Verificador somente leitura compara resumo, sete arquivos e autorização histórica, rejeita alterações ou vínculos simbólicos e reaplica os três controles herdados. Passagem técnica preserva `pending_legal_review`; não há inferência de qualidade jurídica nem novos pontos de aceite |
| 2026-09-24 | Tratar recusa de acesso à busca oficial como impedimento explícito | Uma tentativa delimitada no Falcão abriu a sessão, mas a busca retornou HTTP 403. O adaptador distingue a recusa e não a contorna nem a repete; `JUR-02` continua em revisão, sem novos pontos de aceite |
| 2026-09-24 | Evitar conjuntos incompletos na classificação local do PDF consolidado | Se a segunda saída colidir com um arquivo existente após a checagem inicial ou falhar na serialização, a primeira saída criada pela operação é removida; qualquer arquivo preexistente é preservado. Os testes são sintéticos e não alteram o estado de aceite de `DOM-01` |
| 2026-09-24 | Evoluir classificação documental para contrato v2 sem alterar o significado do v1 | O catálogo v2 acrescenta certidão e comunicação processual, mantém v1 histórico imutável e oferece migração explícita que preserva desconhecidos. Consumidores e testes sintéticos foram ajustados. Ensaio em memória do PDF TRT12: 46/49 classificados; `DOM-01` permanece sem aceite até revisão e calibração independentes |
| 2026-09-24 | Gerar resumos e localizadores processuais em português sem perder custódia histórica | Linha do tempo, posições da parte autora e da reclamada, qualificação e evidência de providências passam a emitir texto e localizadores em português. A matriz aceita também `page/pages` legados. Reexecução apenas em memória do PDF autorizado produziu 49 eventos, três lacunas e 15 posições, com localizadores novos em português; não houve revisão jurídica nem novos pontos de aceite. Fixtures históricas e outros textos gerados ainda exigem auditoria de idioma |
| 2026-09-24 | Reduzir as ferramentas configuráveis dos despachos Codex e registrar o limite remanescente | Relator e triador agora desabilitam shell, pesquisa, aplicativos e subagentes com configuração estrita. Um ensaio real apenas sintético confirmou que o agente não conseguiu ler o arquivo solicitado, mas registrou chamadas de listagem de recursos MCP internos; não se afirma ausência total de ferramentas. Autos reais aguardam limite técnico comprovado, GO específico e revisão jurídica, sem novos pontos de aceite |
| 2026-09-24 | Impedir por código o despacho de autos reais pelo CLI atual | O orquestrador recusa relatório ou matriz diferentes da amostra sintética antes de preparar a saída; relator e triador repetem a recusa antes do modelo. Testes de regressão exercitam os três caminhos e preservam o ensaio simulado. A execução real requer outro transporte validado e revisão da restrição, sem novos pontos de aceite |
| 2026-09-24 | Localizar os textos legíveis do ensaio TRT12 sem alterar contratos estruturados | A amostra sintética de ponta a ponta passa a produzir nomes, resumos, referências de página, evidências e excertos explicativos em português. A minuta apresenta os sete resultados e o período não aplicável em português, enquanto os códigos JSON continuam estáveis para os controles. Cobertura cruzada de Claude e Codex permanece em 24 artefatos; outras fixtures de contrato e mensagens operacionais ainda exigem auditoria de idioma, sem novos pontos de aceite |
| 2026-09-24 | Apresentar em português os comandos locais de segmentação e relatório do PDF do PJe | Ajuda, erros próprios e resumos de execução dos dois comandos foram localizados; o erro de PDF ausente não expõe o caminho do arquivo. Códigos, chaves JSON e regras de custódia continuam iguais. Restam outros comandos e mensagens de bibliotecas dependentes para auditar; sem novos pontos de aceite |
| 2026-09-24 | Localizar a matriz de pedidos e impedir publicação parcial do conjunto protegido | O comando da matriz apresenta descrições, erros próprios e resumo em português, mantendo opções e códigos estruturados. Evidência e matriz são serializadas antes da escrita; se a segunda criação colidir, a primeira saída criada é removida e o arquivo preexistente é preservado. Testes sintéticos não substituem revisão jurídica nem alteram pontos de aceite |
| 2026-09-24 | Localizar diagnósticos do ensaio sintético compartilhado | O executor de Claude Code e Codex informa em português erros próprios de diretório, amostra e contrato; o erro de amostra ausente não divulga seu caminho. As 24 saídas e os identificadores estruturados permanecem iguais. Detalhes de validadores compartilhados e ajuda padrão do interpretador ainda exigem auditoria; nenhum ponto de aceite foi acrescentado |
| 2026-09-24 | Reduzir outras superfícies configuráveis do Codex no ensaio sintético | Além de shell, subagentes, pesquisa e aplicativos, o despacho desabilita navegador, controle do computador e host do modo de código. O CLI instalado aceitou a configuração; relator e triador executaram a amostra sintética e passaram nos validadores, e o gate de qualidade passou com 545 testes. Um ensaio curto não mostrou chamada de ferramenta, mas também não prova ausência de capacidades internas em todos os despachos. Autos reais continuam recusados, sem novos pontos de aceite |
| 2026-09-24 | Iniciar transporte isolado pela Responses API sem ferramentas | Cliente HTTP com destino fixo, `tools: []`, `tool_choice: none`, `store: false`, limites de tamanho e recusa de respostas que contenham chamadas de ferramenta, recusa ou estado incompleto. Testes usam conexão simulada; não houve chamada à API, uso de chave real ou envio de autos. Ainda faltam integração com os agentes, ensaio sintético na API, revisão de privacidade e autorização do provedor. `BLK-11` permanece aberto, sem novos pontos de aceite |
| 2026-09-24 | Ligar o transporte sem ferramentas ao relator e ao triador somente na amostra sintética | Um despachante alternativo reutiliza os prompts, validadores e publicação protegida dos agentes herdados. Pré-verifica a identidade da fixture, a privacidade do diretório e colisões de todas as saídas antes da primeira chamada. Ensaio HTTP simulado produziu narrativa, triagem e rotas válidas; ainda não houve chamada real à API, nem verificação de adequação jurídica. Permanecem ensaio sintético real, revisão de privacidade e autorização do provedor; sem novos pontos de aceite |
| 2026-09-24 | Submeter o caminho sintético pela API aos controles de transferência do pipeline herdado | O despachante alternativo agora executa os três checkpoints compartilhados de custódia da entrada, cobertura da narrativa e cobertura das rotas. Teste com HTTP simulado registra a sequência completa; falha da entrada interrompe antes da primeira requisição. Nenhuma chamada real à API ou revisão jurídica foi realizada; `BLK-11` permanece aberto, sem novos pontos de aceite |
| 2026-09-24 | Recusar respostas da API que não confirmem a política do transporte | O cliente exige que a resposta declare lista vazia de ferramentas, escolha `none`, `store: false` e ausência de conversa ou resposta anterior. Variações e campos obrigatórios ausentes falham antes de publicar texto; testes usam respostas simuladas. O eco desses campos não demonstra retenção zero nem substitui ensaio real ou avaliação do provedor; `BLK-11` permanece aberto, sem novos pontos de aceite |
| 2026-09-24 | Limitar o custo e a extensão do ensaio sintético pela API | A requisição agora define `max_output_tokens: 8192`, abrangendo texto e raciocínio; o teste de contrato confirma o limite enviado. Respostas incompletas continuam recusadas. Não há `OPENAI_API_KEY` neste ambiente, portanto o ensaio real não foi executado e `BLK-11` permanece aberto, sem novos pontos de aceite |
| 2026-09-24 | Separar a autorização do Codex CLI da autorização da API da OpenAI | O contrato vigente `pilot-preflight.v4.schema.json` autoriza os valores `claude` e `codex`, enquanto `codex-pilot-result.v1.schema.json` identifica apenas `codex`. Nenhum dos dois registra autorização específica para envio pela Responses API. O ensaio sintético permanece disponível, mas autos reais não podem usar a autorização `codex` como substituta da autorização do provedor da API. A próxima revisão de contrato deverá distinguir explicitamente superfície, provedor, modelo e condições de tratamento antes de habilitar esse despacho; nenhum ponto de aceite foi acrescentado |
| 2026-09-24 | Tornar explícito o limite dos comandos PJe herdados | Os avisos em português de `pje-download` e `capturar-sessao-pje` agora proíbem executar o fluxo legado do TRF5 como se fosse o adaptador TRT12. A captura e a autenticação do TRT12 continuam dependentes do mapa autorizado e revisado; esta alteração documental não demonstra integração com o PJe nem altera pontos de aceite |
| 2026-09-24 | Criar registro suplementar de autorização específica da API | O esquema `openai-api-authorization.v1` e seu verificador vinculam a Responses API a piloto, processo, escopo, classificação de acesso, modelo, responsável, prazo e controles sem ferramentas/armazenamento. Testes sintéticos recusam autorização `codex` reutilizada, outro processo ou escopo, validade vencida, controles incompatíveis e arquivo sem proteção. O resultado informa apenas vínculo, nunca `GO`; identidade declarada e condições do provedor ainda exigem revisão externa. Não existe despacho de autos reais pela API e `BLK-11` permanece aberto, sem novos pontos de aceite |
| 2026-09-24 | Integrar tecnicamente o piloto da API ao fluxo herdado sem habilitar autos reais | `run_openai_pilot.py` combina a verificação prévia v4, a autorização suplementar, entrada protegida, relator e triador herdados e os três controles de transferência; um resumo próprio mantém o vínculo ao registro da API e a revisão jurídica pendente. Testes com fronteira HTTP substituída percorrem o caminho técnico e recusam autorização ausente/vencida, outro processo e colisão. `REAL_CASE_DISPATCH_ENABLED = False` bloqueia qualquer envio real nesta versão, inclusive com registros declaratórios preenchidos. Permanecem ensaio sintético real na API, análise de privacidade e revisão humana; sem novos pontos de aceite |
| 2026-09-24 | Conferir independentemente o resultado técnico do piloto pela API | `verify_openai_pilot_result.py` recompõe a ligação do resumo com autorização, processo, modelo, hashes e três controles de transferência sem chamar o modelo. Testes simulados aprovam o resultado íntegro e recusam mudança na autorização, na narrativa, no modelo declarado ou vínculo simbólico. O estado continua `pending_legal_review`; o despacho real permanece desabilitado e nenhuma pontuação foi concedida |
| 2026-09-24 | Auditar o reuso dos seis agentes probatórios herdados antes de habilitá-los no TRT12 | A auditoria distingue observações de fonte reaproveitáveis de checklists e exemplos penais ou de outros ramos. Prioriza adaptação documental por pedido, posterga revisão testemunhal/pericial/digital, retira confissão criminal do MVP e exclui reconhecimento penal do perfil. Nenhum agente foi despachado ou validado juridicamente; a análise orienta a próxima implementação, sem novos pontos de aceite |
| 2026-09-24 | Preparar fonte literal delimitada para futura revisão documental por pedido | O novo preparador seleciona IDs de evidência do mesmo pedido, confere o PDF contra seu sumário nativo e SHA-256, extrai apenas páginas dos documentos correspondentes e grava um pacote privado sem sobrescrita. Testes com PDF sintético cobrem seleção, custódia, mapa de páginas alterado, falta de texto, isolamento e CLI sem vazamento de conteúdo. Ainda não executa agente, OCR ou juízo probatório; nenhuma pontuação jurídica foi concedida |
| 2026-09-24 | Definir a saída do agente documental por pedido e conferir citações no PDF | A variante TRT12 do agente herdado não atribui força probante e emite observações por `evidence_id` com estado pendente ou insuficiente. Um contrato v1 e validador local conferem cobertura, identidade do pacote, documento, página e literalidade contra PDF sintético. Ainda faltam confronto com autos autorizados, conferência visual e revisão jurídica; nenhum ponto de aceite foi concedido |
| 2026-09-24 | Ensaiar a variante documental no Codex com fonte fictícia controlada | O executor gera internamente PDF e matriz sintéticos, prepara o pacote por evidência, despacha com superfícies configuráveis desabilitadas e só publica saídas após validação. Um despacho real pelo `codex-cli 0.155.0-alpha.16.3` devolveu `pending_human_review`, citou literalmente a página 2 e passou no validador; o modelo padrão do CLI não foi fixado. Não houve envio de autos reais, avaliação jurídica ou integração à etapa condicional do manifesto. O marco não altera pontos de aceite |
| 2026-09-24 | Vincular a observação documental à trilha probatória e fixar o modelo do ensaio | A ponte exige rota `evidence_analysis`, cobertura de todas as evidências do pedido e trecho literal válido; deriva `evidence-review` sem `assessment` e recibo condicional `linked` ou `gap`. O ensaio Codex com `--model gpt-6-sol` publicou observações e os dois fragmentos protegidos, com hashes no resumo; o identificador é o modelo solicitado, não o snapshot interno comprovado. A etapa do manifesto ainda não consome esses fragmentos, e revisão jurídica e autos reais permanecem pendentes. Sem novos pontos de aceite |
| 2026-09-24 | Compor a etapa condicional completa a partir da observação documental | O compositor local exige pacote validável para cada pedido encaminhado à prova, combina recibos das demais trilhas e submete os artefatos completos ao checkpoint `execute-conditional-tracks`. Testes sintéticos cobrem aceite, abstenção, citação inventada, recibo probatório externo, colisão e reversão após recusa. Ainda não há despacho automático pelo manifesto, execução com autos reais ou revisão jurídica; sem novos pontos de aceite |
| 2026-09-24 | Vincular a composição documental à retomada do manifesto compartilhado | O executor local revalida os sete checkpoints anteriores, exige `execute-conditional-tracks` como próxima etapa e registra o checkpoint depois de compor. Teste com dados fictícios avança para `analyze-claims` e recusa a etapa sem `route-claims` aceito. Com `state_output`, publica também o estado em `0600`, sem sobrescrita; colisões e tentativas inválidas deixam as saídas da etapa ausentes. O agente ainda não é despachado automaticamente e autos reais continuam fora desse ensaio; sem novos pontos de aceite |
| 2026-09-24 | Vincular o checkpoint probatório à fonte lida pelo agente | O compositor publica registro auxiliar privado com PDF, segmentos, pacote e observações por pedido. A revisão aceita contém hashes do pacote e das observações; a retomada reconfere o PDF e invalida `execute-conditional-tracks` se a fonte mudar ou o registro desaparecer. O contrato v1 anterior sem observação automática continua aceito para as amostras históricas. O vínculo não comprova interpretação jurídica nem despacho automático com autos reais; sem novos pontos de aceite |
| 2026-09-24 | Despachar a variante documental sintética e importar sua saída protegida para o pipeline | O importador confere hashes, instruções do agente, matriz, PDF fictício e fragmentos antes da cópia privada e do checkpoint; o despachante exige `route-claims` reutilizável antes de chamar o Codex. Testes com resposta simulada chegam a `analyze-claims` e barram saída alterada ou triagem ausente. Um despacho local efetivo pelo Codex CLI com `gpt-6-sol` chegou a `execute-conditional-tracks` aceito e revisão `pending_human_review`. Isso ainda não generaliza pedidos ou PDFs reais, não representa revisão jurídica e não concede novos pontos de aceite |
| 2026-09-24 | Preparar pacotes documentais para todos os pedidos probatórios do caso | O preparador em lote reutiliza a seleção e a custódia do PDF existentes, separa o texto por pedido e publica índice, segmentos e pacotes privados sem sobrescrita. Testes com dois pedidos fictícios cobrem isolamento, rejeição integral de um pedido inválido, CLI sem texto-fonte no terminal e composição condicional com ambos. Ainda não há despacho de modelo para autos reais, conferência visual nem revisão jurídica; sem novos pontos de aceite |
| 2026-09-24 | Carregar observações protegidas por pedido no checkpoint documental | O carregador compara o índice de pacotes às rotas e evidências vigentes, recusa observação ausente ou pacote alterado e reconfere citações literais no PDF. Um vínculo ao executor de retomada aceita os arquivos locais sem montar pacotes manualmente; testes fictícios alcançam `analyze-claims` e confirmam ausência de publicação quando falta observação. Não despacha modelo nem valida interpretação jurídica; sem novos pontos de aceite |
| 2026-09-24 | Abrir a etapa anterior à matriz de provas com fontes por documento para o inventariador herdado | O preparador local vincula cada documento do sumário do PJe ao PDF e à matriz de pedidos, separa alegações de texto literal e publica pacotes privados para todos os documentos, com reversão integral em falha. Testes fictícios cobrem isolamento das páginas, texto ausente, colisão e CLI sem exibir autos. Verificação somente leitura do PDF TRT12 já fornecido encontrou 134 páginas, 49 documentos, nenhuma página sem texto extraível e maior documento de 16 páginas; não foi gerado inventário nem matriz desse caso. O agente, sua saída estruturada e a revisão humana ainda faltam; sem novos pontos de aceite |
| 2026-09-24 | Adaptar a saída descritiva do inventariador herdado ao TRT12 | A variante por documento emite itens `INV-DOC-xxx-nnn` pendentes de revisão, com proposta de vínculo a pedidos, trecho literal e limitação; não atribui `EVD-xxx` nem valora provas. O contrato e o validador reconstruem o pacote do PDF e recusam trecho inventado, página de outro documento, pedido desconhecido, pacote alterado, cobertura vazia sem justificativa e posição da matriz ligada a documento ausente. Testes usam PDF fictício e CLI sem exibir fonte; ainda faltam execução com autos autorizados, conferência de exaustividade e seleção humana para `evidence-matrix.json`. Sem novos pontos de aceite |
| 2026-09-24 | Fechar a cobertura técnica do lote de observações probatórias | O validador de lote exige um resultado para cada documento do PDF e recusa ausências, extras, índice ou matriz alterados, pacote incompatível e resultado vinculado; reexecuta a conferência literal por documento e publica somente contagens. O ensaio usa PDF fictício; `no_item_identified` e `insufficient` continuam lacunas expressas. Não houve execução do inventariador sobre autos reais, validação de exaustividade ou revisão jurídica; sem novos pontos de aceite |
| 2026-09-24 | Ensaiar o inventariador herdado no Codex com todos os documentos fictícios | `run_codex_inventory_rehearsal.py` reutiliza o despacho Codex restrito, gera PDF fictício de dois documentos e publica o lote protegido apenas após validar todas as respostas. Testes simulados bloqueiam falta de autorização sintética, arquivo existente, segundo trecho inventado e omissão do registro fictício conhecido. Uma execução real solicitando `gpt-6-sol` produziu dois itens descritivos, um por documento; ambos ficaram sem associação automática a pedido e com limitações. A conferência independente do lote passou, arquivos `0600`. O identificador do modelo é o solicitado, não prova do snapshot; nenhum auto real foi enviado ou validado, e não houve revisão jurídica. Sem novos pontos de aceite |
| 2026-09-24 | Preparar a seleção humana anterior à matriz de provas | `review_evidence_inventory.py` gera registro privado com decisões `pending` para cada item e confirmação por documento; o validador revalida fontes, cobertura, pedidos conhecidos, justificativas e pendências, sem criar `evidence-matrix.json`. Testes fictícios cobrem alteração de trecho, pedido desconhecido, documento não lido, decisão ausente, adiamento e inventário insuficiente. Um registro pendente foi gerado a partir do ensaio Codex fictício: dois documentos e dois itens, nenhuma seleção. Revisão jurídica real, conferência visual e construção da matriz permanecem abertas; sem novos pontos de aceite |
| 2026-09-24 | Reutilizar o construtor herdado para candidatos após revisão declarada | O registro agora separa `source_type` sugerido de `selected_type` escolhido pelo revisor. `build_reviewed_evidence_candidates.py` chama `build_evidence_matrix.py` somente com revisão completa e sem pendências; publica candidatos e proveniência `INV` → `EVD`, com hashes e trechos, fora do nome canônico. Testes fictícios cobrem tipo corrigido, pedido, localizador, estado `pending`, exclusão com pedido descoberto, bloqueio de adiamento/omissão/ausência de revisão e não sobrescrita. Nenhuma revisão jurídica real ocorreu, e `evidence-matrix.json` não é criada; sem novos pontos de aceite |
| 2026-09-24 | Conferir independentemente os candidatos probatórios publicados | `verify_reviewed_evidence_candidates.py` reconstrói as saídas a partir da revisão e das fontes atuais e compara integralmente os arquivos publicados, sem modificá-los. Testes fictícios cobrem alterações nos candidatos, na proveniência e na revisão, arquivo ausente e CLI sem trecho-fonte. A conferência não autentica o revisor, não aprova a seleção jurídica nem cria `evidence-matrix.json`; sem novos pontos de aceite |
| 2026-09-24 | Tornar a revisão do inventário navegável sem automatizar decisões jurídicas | `prepare_evidence_inventory_review_packet.py` organiza páginas, itens, trechos e limitações num roteiro privado `0600` antes de editar o registro de revisão. Testes fictícios cobrem cobertura documental, ausência de decisão automática, fonte alterada, não sobrescrita e terminal sem texto-fonte. O roteiro não substitui o PDF nem a revisão jurídica; o processo real ainda não recebeu inventário validado. Sem novos pontos de aceite |
| 2026-09-24 | Exercitar o preparo local de fontes com o PDF TRT12 já fornecido | Verificação somente local e sem envio ao modelo confirmou 134 páginas, 49 documentos, 46 classificações e três tipos desconhecidos. O relatório diagnóstico preservou oito pedidos e sete posições de defesa; a matriz em memória registrou 16 providências e seis lacunas de associação. A primeira página da única contestação foi conferida visualmente para vincular o documento à parte correspondente. `prepare_evidence_inventory_packets.py` gerou 49 pacotes `0600` em diretório temporário, com maior arquivo de 34.346 bytes; a cópia e os derivados temporários foram removidos, e o PDF original ficou intacto. O valor `public_or_authorized` foi usado apenas no ensaio em memória, sem certificar o regime de acesso. Ainda faltam classificação dos três tipos, inventário dos documentos, autorização de retenção dos derivados, conferência jurídica e execução controlada do modelo com autos reais; sem novos pontos de aceite |
| 2026-09-24 | Proteger e localizar o formulário de inventário cego dos pedidos | `prepare_claim_blind_review.py` agora recusa diretório de saída compartilhado ou vinculado e preserva até vínculos quebrados no nome de saída. Descrições das opções, erros próprios e resultado estão em português; cabeçalhos padrão do `argparse` ainda requerem auditoria geral de idioma. O PDF TRT12 fornecido passou na geração apenas em memória de formulário vazio para as páginas 1–13 da petição inicial, sem IDs ou contagens extraídos pelo sistema. Testes sintéticos cobrem privacidade da saída, não sobrescrita, custódia, pseudônimo e CLI. O formulário não foi guardado para revisão, não certifica sigilo nem constitui avaliação jurídica; sem novos pontos de aceite |
| 2026-09-24 | Localizar e proteger a linha do tempo do processo | `build_procedural_timeline.py` mantém códigos JSON e resumos já localizados, mas agora apresenta descrição, opções e diagnósticos próprios em português e recusa diretório de saída compartilhado, vinculado ou dentro do repositório. Cabeçalhos padrão do `argparse` ainda ficam em inglês. Testes sintéticos verificam eventos, lacunas, ausência de conteúdo processual no terminal e criação protegida. A mudança não resolve as três classificações desconhecidas do PDF TRT12 nem comprova revisão jurídica; sem novos pontos de aceite |
| 2026-09-24 | Localizar os diagnósticos da verificação prévia do piloto | `validate_pilot_preflight.py` apresenta descrição, erros próprios e resultado em português, mantendo chaves JSON, estados e decisões de bloqueio. Testes do comando e do contrato foram atualizados; o gate local passou com 703 testes. Erros detalhados de validadores compartilhados e cabeçalhos padrão do `argparse` ainda podem sair em inglês. Não houve execução com autos reais, autorização nova nem pontos de aceite |
| 2026-09-24 | Localizar o validador compartilhado de esquemas JSON | `schema_validation.py` passa a comunicar em português os erros de leitura, referência, tipo, campo, lista, texto e limite numérico sem alterar caminhos nem identificadores do contrato. Testes diretos e consumidores históricos preservam a recusa de campos extras. A localização dos validadores próprios e dos cabeçalhos da ajuda ainda não está concluída; não houve novo ponto de aceite |
| 2026-09-24 | Vincular candidatos probatórios revisados à matriz canônica somente com aprovação declarada | `promote_reviewed_evidence_matrix.py` revalida candidatos e fontes, exige registro privado com hashes, revisor, função, horário posterior à revisão e reconhecimento dos pedidos sem prova, então publica `evidence-matrix.json` e recibo `0600` sem sobrescrita. A conferência posterior recusa alteração da aprovação ou da matriz. O controle `build-decision-units` recusa o caminho de inventário quando a promoção não é verificável, mantendo o ensaio sem inventário compatível. Testes usam PDF e revisão fictícios; a identidade/qualificação do revisor não é autenticada, não houve revisão jurídica real nem aceite de `DOM-04`. O avanço ponderado permanece 30,0% |
| 2026-09-24 | Provar a aceitação positiva da matriz promovida pelo checkpoint herdado | Ensaio de integração monta inventário, revisão, candidatos e aprovação fictícios, transporta os arquivos privados para a amostra compartilhada e confirma que `build-decision-units` aceita a matriz canônica íntegra e recusa o mesmo conjunto sem recibo. A primeira falha observada foi somente o caminho temporário não resolvido no teste (`/var`/`/private/var` no macOS), ajustado conforme o contrato já existente do gate. O teste não representa revisão jurídica real ou execução com autos, sem novos pontos de aceite |
| 2026-09-24 | Adaptar e ensaiar o analisador herdado por pedido no TRT12 | A variante `analisador-marmelstein-trt12.md` preserva exame imparcial das versões e objeções, emite `claim-analysis.json` por pedido e é vinculada a `analyze-claims` com resumo das instruções verificável nos dois ambientes. O ensaio sintético Codex com `gpt-6-sol` foi inicialmente recusado por citar o ID de uma referência jurídica fictícia como precedente; depois da instrução distinguir custódia de fonte conferida, a repetição passou no checkpoint com `pending_human_review`, sem fatos, regras ou precedentes tomados como verificados. O SHA-256 da análise aceita é `0d6f52039ba27748b5dd96ba59817c50516ceb2abe29bc30f3eebcad4a71eabf`. O ID do modelo é o solicitado ao CLI; não há aferição jurídica, despacho integrado ao executor retomável, adaptação de fundamentador/redator, novo ponto de aceite nem uso de autos reais |
| 2026-09-24 | Registrar a análise por pedido no checkpoint compartilhado | `run_claim_analysis_stage.py` exige que `analyze-claims` seja a próxima etapa reutilizável, publica JSON privado sem sobrescrita e só devolve estado atualizado depois do controle de cobertura. Testes sintéticos avançam da etapa documental para `draft-judgment` e recusam conclusão de mérito sem revisão, retirando a saída recém-criada. `save_execution_state_once` foi compartilhado com a etapa documental para manter a escrita exclusiva do checkpoint. A origem do JSON ainda não é conferida contra o resumo do ensaio Codex e não há despacho automático, avaliação jurídica ou novo ponto de aceite |
| 2026-09-24 | Importar a análise Codex fictícia somente quando corresponder ao checkpoint | `import_codex_claim_analysis_rehearsal.py` confere arquivos privados, hashes, versão do agente, modelo/modo declarado, plano Codex e igualdade exata dos sete insumos usados pelo modelo com os do checkpoint atual, além de índice e cargas sintéticos. Testes recusam resposta alterada, insumo atual divergente e plano Claude. Uma resposta anterior do Codex CLI solicitando `gpt-6-sol` entrou no checkpoint sintético e a retomada apontou `draft-judgment` com nove etapas reutilizáveis. O importador não autentica o serviço nem aceita a saída variável da ponte documental; naquela etapa ainda faltava despachar o modelo com os insumos atuais, sem novo ponto de aceite |
| 2026-09-24 | Despachar o analisador herdado com a revisão documental fictícia atual | `run_codex_claim_analysis_stage.py` exige origem sintética exata e revisão derivada da observação validada no PDF, envia sete insumos atuais ao Codex e só publica análise pendente com recibo privado e controle de cobertura. Testes recusam revisão desvinculada, estado ocupado e tentativa inválida antes do despacho. A execução efetiva das etapas documental e de análise com `gpt-6-sol` chegou a nove checkpoints; a próxima é `draft-judgment`, com análise SHA-256 `518a4ee11e355110ad47725983e07b1779296223ff1bc76733cc5f6a56f8f24c`. Nenhum auto real foi enviado, não há validação jurídica, assinatura do serviço ou ponto novo de aceite; avanço ponderado continua 30,0% |
| 2026-09-24 | Despachar o fundamentador herdado com análise documental fictícia atual | `run_codex_draft_stage.py` confere recibo da análise, resumo reconstruído do comando anterior, sete insumos atuais e custódia da observação no PDF fictício antes de chamar o Codex. Testes recusam recibo adulterado e colisão do estado antes do envio; publica dispositivo e minuta apenas após `draft-congruence`, com recibo privado. Execução efetiva encadeada com `gpt-6-sol` chegou a dez checkpoints e apontou `merge-judgment`; hashes do dispositivo e da minuta: `136ddb502355b66c7dc64ad1023b2395d8e7b4985464feaca4263145f6afaf6d` e `ce857eaf6ceeff23bd5ec434d7d79410aed05512b98ae418237f8d8f5e3f31ec`. Resultado `pending_human_review`; sem autos reais, certificação jurídica, autenticação do serviço ou novo ponto de aceite. Avanço ponderado: 30,0% |
| 2026-09-24 | Adaptar o fundamentador herdado ao dispositivo TRT12 e ligar a etapa de minuta | A variante `fundamentador-marmelstein-trt12.md` mantém argumentação clara por pedido, mas exclui comandos federais, assinatura e texto livre; o manifesto a vincula a `draft-judgment`. `run_draft_judgment_stage.py` renderiza a minuta do dispositivo e da análise atuais, publica ambos com permissão privada, registra o décimo checkpoint e os retira se houver comando para pedido pendente. Testes com dados fictícios passaram; ainda não houve despacho efetivo do fundamentador, análise de autos reais ou revisão jurídica. `DOM-06` e o progresso ponderado permanecem sem novos pontos de aceite |
| 2026-09-24 | Executar e importar o fundamentador Codex em amostra fictícia | `run_codex_draft_rehearsal.py` aceita somente análise anterior com resumo e hashes conferidos, envia insumos fictícios ao agente sem ferramentas configuráveis, exige dispositivo sem comando e valida a minuta determinística. O Codex CLI solicitado com `gpt-6-sol` produziu `pending_human_review`; `import_codex_draft_rehearsal.py` importou essa saída após conferir recibos, agente, análise atual e insumos fixos, alcançando dez checkpoints e `merge-judgment` como próximo. Uma minuta alterada não é publicada. Não houve autos reais, validação jurídica nem importação de insumos documentais variáveis; `DOM-06` permanece em andamento e o avanço ponderado segue 30,0% |
| 2026-09-24 | Fundir a minuta aceita e conservar o bloqueio final | `run_merge_judgment_stage.py` copia literalmente a minuta para o arquivo do processo somente após o checkpoint anterior, com acesso privado, publicação única e reversão se o controle falhar. Testes recusam minuta alterada. A cadeia com as respostas efetivas do Codex CLI alcançou onze checkpoints; `review-and-gate` continua recusado porque `pending_human_review` não é decisão judicial. Não houve novo ponto de aceite nem alteração dos 30,0% |
| 2026-09-24 | Repetir a fusão após as etapas documentais atuais | Execução efetiva do Codex CLI com a observação documental, análise e fundamentação fictícias atuais alcançou onze checkpoints. `run_merge_judgment_stage.py` preservou literalmente a minuta no arquivo por processo: ambos tiveram SHA-256 `cbbcafb35640498251f03998a68ff853046ae1f71bd2bacb44565ed7477dd80d`. A retomada apontou `review-and-gate`, cuja aceitação foi recusada pelo pedido `pending_human_review`. O ensaio não incluiu autos reais ou revisão jurídica e não muda o avanço ponderado de 30,0% |
| 2026-09-24 | Impedir que o nome de um PDF processual entre nos arquivos versionáveis | A auditoria encontrou no teste documental um identificador do processo real usado apenas em asserção negativa; ele foi substituído por expressão genérica. `runtime/data-hygiene-contract.json` passou a recusar basenames `Processo_` seguidos de número CNJ, com ou sem `.pdf`, sem imprimir o valor encontrado. Dois testes com número inteiramente fictício reproduziram a falha e confirmaram a recusa; a varredura atual não encontrou o identificador real no repositório. Isso protege a preparação do commit, mas não comprova revisão jurídica nem altera os 30,0% |
| 2026-09-24 | Reexecutar relator e triador Codex e proteger a materialização sintética | A amostra versionada gerou 24 artefatos em diretório temporário privado; o resumo do contrato foi `8bc0f992871b3afaf71a2cb13af314ebbf1fbef49580bfa275462052be37a07e`. Relator e triador foram despachados efetivamente pelo Codex CLI com `gpt-6-sol`, sem autos reais; narrativa e triagem tiveram SHA-256 `82f5bcc8a77fca9673eaf50b9306d7fddfd40c335c2c0e129d04fa36834ab102` e `090a892e037fd9435535cafd2a02785e8ec995b348be04f54c1c0e50887aae26`. Os três controles de transferência aceitaram as saídas, gravadas em modo `0600`. O ensaio revelou que o gerador sintético gravava artefatos em `0644`; o commit `3df2db7` passou a exigir diretório privado, recusar vínculo simbólico e gravar arquivos `0600`, com 411 testes em checkout isolado. A árvore local passou 751 testes. O controle global da amostra foi calculado antes das novas respostas dos agentes; este ensaio não comprova aceite jurídico nem eleva os 30,0% |
| 2026-09-24 | Distinguir o fork TRT12 do plugin original e suspender os disparos automáticos da CI | O README principal passou a apontar para o plano, o roteiro e o manual do operador, com limite expresso para autos reais; a instalação pelo marketplace foi identificada como capacidade herdada, não como instalação TRT12. O workflow de qualidade preserva a execução manual, mas deixa de disparar em push e solicitação de alteração conforme pedido do usuário. A evidência histórica de `FND-02` permanece válida; enquanto a CI automática estiver suspensa, cada alteração depende do controle local antes de publicação. Não há novos pontos de aceite; avanço ponderado de 30,0% |
| 2026-09-24 | Localizar as justificativas do controle final sem alterar seus códigos | `evaluate_final_gate.py` agora emite detalhes de congruência, citação, fonte e cálculo em português, além de mensagens próprias de recusa e contrato. Os valores enumerados, IDs e chaves de `global-gate.json` permanecem estáveis; motivos fornecidos pelo operador são preservados literalmente. Testes de regressão passaram primeiro pela falha esperada e depois pela saída localizada. A alteração não valida mérito jurídico nem acrescenta pontos aos 30,0% |
| 2026-09-24 | Preparar a revisão humana final sem promover a minuta | `prepare_final_human_review.py` reaplica o controle de fusão, vincula por SHA-256 os arquivos apresentados e cria roteiro privado com conferência por pedido e campos jurídicos vazios. Testes sintéticos recusam minuta alterada, fonte vinculada simbolicamente, saída ocupada e espaço público. O roteiro não autentica o revisor, não registra decisão no checkpoint e não transforma `pending_human_review` em aceite; revisão qualificada e autos autorizados continuam pendentes, sem novos pontos além dos 30,0% |
| 2026-09-21 | Matrizes de provas preservam fontes, cobertura dos pedidos, limitações e contradições simétricas | `DOM-04` avança sinteticamente sem alegar completude probatória antes da revisão cega |
| 2026-09-21 | Cada pedido recebe um encaminhamento explicável ou abstenção explícita | `DOM-05` rejeita perda silenciosa de pedidos e solicitações incoerentes de trabalho antes da calibração real |
| 2026-09-21 | Análise, resultado, dispositivo e minuta mantêm vínculos por IDs estáveis | `DOM-06` avança sinteticamente sem tratar minuta não revisada como ato judicial pronto para assinatura ou publicação |
| 2026-09-21 | Usuário aprovou blueprint, roadmap, sequência, limites de extensão, rastreabilidade, medição e limite de automação | `ARC-01` aceito; Trilha A atinge 3% e progresso ponderado, 1,8% |
| 2026-09-21 | CI remota e revisões focadas de fundação e arquitetura passaram | `FND-02` a `FND-04` e `ARC-02` a `ARC-05` aceitos; Trilha A atinge 18% e progresso ponderado, 10,8% |
| 2026-09-21 | Pesquisa do TST usa consulta pública e documentos oficiais, HTTPS limitado e custódia literal | `JUR-01` aceito; consulta CNJ exata usa filtro oficial estruturado e estado não normalizado do precedente fica explícito |
| 2026-09-21 | Jurisprudência atual do TRT12 usa coleções oficiais de sentenças e acórdãos do Falcão, com cobertura legada explícita | `JUR-02` em revisão com evidência determinística; aceite aguarda verificação real e delimitada da custódia após fim do limite de consultas |
| 2026-09-21 | Precedentes regionais usam acompanhamento de IRDR vinculado pelo tribunal e página oficial de teses, com leitura conservadora | `JUR-03` aceito; suspensão atual difere da histórica, ausência de IAC é explícita e teses IUJ atuais/canceladas conservam fontes oficiais |
| 2026-09-21 | Consolidação de precedentes preserva fontes dos provedores e divergências explícitas de estado | `JUR-04` aceito; fontes equivalentes seguem hierarquia determinística, apelidos descartados são auditáveis e `unknown` não substitui estado explícito |
| 2026-09-21 | Etapas aceitas só são reutilizadas por checkpoint neutro quanto ao ambiente e vinculado a contratos, fontes, dependências, saídas e controles vigentes | `PIP-01` aceito; Claude Code e Codex compartilham evidência de retomada, com despachos separados; etapas desatualizadas invalidam dependentes |
| 2026-09-21 | Trabalho condicional deriva apenas de sinalizadores aceitos de encaminhamento por pedido | `PIP-02` aceito; trilhas desabilitadas não são acionadas, abstenção segue válida e pedidos encaminhados não perdem tarefas silenciosamente |
| 2026-09-21 | Artefatos de decisão exigem controle independente de congruência após geração | `PIP-03` aceito; cada pedido exige análise não vazia, dispositivo, resultado, fonte e custódia exata da minuta antes de atingir 100% |
| 2026-09-21 | Aceite final combina relatório legível por máquina e aplicação obrigatória | `PIP-04` aceito; citações longas sem suporte e cálculos divergentes falham, indisponibilidades bloqueiam com motivo e relatório reprovado não prossegue |
| 2026-09-21 | Aceite entre ambientes usa um caso sanitizado e grafo compartilhado de artefatos | `PIP-05` aceito; Claude Code e Codex geram as mesmas 19 saídas e controle final em espaços limpos, com vínculos próprios de despacho |
| 2026-09-21 | Obtenção de documentos do PJe separa índice completo de metadados e download solicitado | `PJE-04` avança na interface compartilhada; bytes devem corresponder ao SHA-256 indexado, itens pulados continuam visíveis e indisponibilidade vira lacuna explícita |
| 2026-09-21 | Limites de aceite histórico e campos de revisão são congelados antes de observar resultados | `VAL-01` aceito; desenvolvimento e reserva intocada ficam separados, ausência não equivale a aprovação e defeitos críticos/altos têm tolerância zero |
| 2026-09-21 | Recuperação da obtenção pelo PJe vincula requisição, catálogo, conteúdo e tentativas a evidências imutáveis | `PJE-05` avança sinteticamente sem baixar de novo conteúdo aceito nem tratar esgotamento de tentativas como sucesso; aceite empírico depende de ensaios TRT12 autorizados |
| 2026-09-21 | Prontidão do host exige executar MCP e OCR em português, não apenas instalar pacotes | `FND-01` aceito após importar cinco servidores MCP e executar conversão real Poppler–Tesseract no macOS; M0 alcançado |
| 2026-09-21 | Respostas iniciais do Falcão são validadas por endpoint, não forçadas a um JSON único | `JUR-02` aceita lista de notificações e objeto de preenchimento automático; busca/detalhe exigem objeto, e a consulta real posterior bloqueou no limite oficial |
| 2026-09-21 | Manual do operador só é aceito após execução de checkout remoto limpo | `OPS-01` aceito após ensaio macOS reproduzir prontidão, controle de qualidade e saídas sintéticas idênticas e aprovadas em Claude Code/Codex |
| 2026-09-21 | Piloto real continua proibido até aprovação explícita de responsáveis e retenção | `OPS-02` avança com controles de incidente, reversão, recuperação e revisão humana; registro em branco não autoriza processamento |
| 2026-09-21 | Responsáveis e prazos padrão de retenção foram aprovados | `OPS-02` aceito e M7 alcançado; cada processo ainda exige verificação prévia `NO-GO` e revisão jurídica humana obrigatória |
| 2026-09-21 | Pontuação da revisão cega segue protocolo congelado, com desenvolvimento antes da reserva intocada | `VAL-02` avança com indicadores determinísticos, exclusões de dados ausentes, custódia de etapa/gravidade e tolerância zero; 15 casos de desenvolvimento precedem correções e cinco ficam sem nota até `VAL-03` |
| 2026-09-21 | Correções históricas vinculam-se a revisões e eliminam defeitos materiais antes de pontuar a reserva | `VAL-03` avança com custódia de correções, regressão, nova medição e contrato separado de aprovação dos cinco casos; evidência sintética não gera pontos |
| 2026-09-21 | Dossiê histórico não promove evidência pendente, rejeitada, `no_go`, divergente ou com defeito material | `VAL-04` avança com custódia do resumo da fonte, limites, falhas, aprovação humana, escopo local supervisionado e proibição permanente de atos judiciais externos |
| 2026-09-21 | Cada processo real exige verificação prévia por máquina, não apenas lista textual | Sigilo, acesso excepcional, evidência vencida, divergência do mapa, retenção excessiva, dados no repositório, saída não vazia, divergência entre ambientes e atos externos bloqueiam o piloto |
| 2026-09-21 | Captura normal do PJe não deve provocar falha de autenticação ou provedor só para obter cobertura | Lacunas funcionais de endpoints bloqueiam; grupos de falhas não observados naturalmente seguem explícitos para evidência separada e autorizada |

---

## 11. Bloqueios e insumos atuais

| ID | Insumo ou decisão | Impede | Situação |
|---|---|---|---|
| BLK-01 | Aprovação expressa do plano arquitetural e do roteiro | ARC-01 | Encerrado em 2026-09-21 |
| BLK-02 | Captura HAR autorizada do primeiro grau do TRT12 | PJE-01 e seguintes | Aberto |
| BLK-03 | Autorização e registro de tratamento dos dados para cada processo; processos sigilosos continuam proibidos | Casos reais e ensaios de obtenção pelo PJe | Aberto; o contrato de verificação prévia está pronto, mas faltam registro de processo não sigiloso e revisor jurídico identificado |
| BLK-04 | Amostra histórica aprovada e disponibilidade de revisor | VAL-02 e seguintes | Aberto; a pontuação determinística está pronta, mas faltam 20 processos autorizados e revisor qualificado |
| BLK-05 | Estilo de sentença do gabinete ou documento-modelo aprovado | DOM-06 | Aberto |
| BLK-06 | Python 3.10+ no macOS de destino para executar servidores MCP locais | Aceite de FND-01 e servidores MCP | Encerrado em 2026-09-21 com Python 3.12.14 e MCP 1.30.0 |
| BLK-07 | Tesseract com dados de português e Poppler instalado pelo usuário | Ensaio de OCR de FND-01 | Encerrado em 2026-09-21 com Tesseract 5.5.3, dados de português, Poppler 26.05 e OCR executado |
| BLK-08 | Commit ou solicitação de alteração e primeira execução remota do GitHub Actions | Evidência de aceite de FND-02 | Encerrado pela execução 35657051683 |
| BLK-09 | Acesso à busca oficial do Falcão ainda indisponível para a verificação delimitada | Evidência real de aceite de JUR-02 | Tentativas de 2026-09-21 atingiram o limite de consultas; uma tentativa em 2026-09-24 abriu a sessão, mas recebeu HTTP 403 na busca. A causa do 403 não foi estabelecida; não repetir nem contornar sem esclarecimento da política de acesso |
| BLK-10 | Responsáveis pelo piloto e prazos de retenção dos dados judiciais aprovados | Aceite de OPS-02 e autorização do piloto real | Encerrado em 2026-09-21 por aprovação expressa; cada processo ainda exige autorização e revisor |
| BLK-11 | Limite técnico de ferramentas e leitura local no despacho do modelo | Primeira execução do piloto com autos reais via Codex | Aberto; o caminho CLI atual recusa autos reais por código, pois a configuração das superfícies não certifica ausência de capacidades internas. O despachante alternativo da Responses API está integrado somente ao ensaio sintético, declara zero ferramentas e recusa saídas inesperadas em testes simulados. O registro suplementar da API agora tem contrato e verificador de vínculo, mas não substitui a autorização humana nem o `GO` por processo. Ainda faltam ensaio sintético real, validação de privacidade e caminho real condicionado a ambas as autorizações antes de qualquer transmissão de autos |

Bloqueios abertos não impedem trabalho independente na base e nos contratos.

---

## 12. Próxima sequência de aceite

A sequência recomendada após a aprovação do plano arquitetural é:

1. Adaptar e executar o relator herdado e o triador no perfil TRT12, usando a
   entrada protegida do relatório e da matriz e a verificação de rotas por
   pedido; separar a pontuação sintética da execução real dos agentes.
2. Designar revisor qualificado para ler e congelar o inventário protegido de
   pedidos a partir das fontes, antes de ver a saída do sistema. Depois,
   compará-lo aos oito vínculos entre pedidos e providências, duas alternativas
   condicionais, seis itens acessórios sem vínculo e códigos sem suporte,
   registrando correções adjudicadas em nova versão protegida.
3. Higienizar uma captura local autorizada do primeiro grau do TRT12 e revisar
   o mapa de endpoints para `PJE-01`.
4. Completar o registro protegido do processo, passar na verificação prévia
   executável e preparar os três insumos do mesmo processo no piloto controlado.
5. Vincular o classificador de estado da sessão a uma consulta TRT12 do mapa revisado.
6. Vincular a descoberta de tarefas e processos aos endpoints TRT12 revisados.
7. Esclarecer a recusa HTTP 403 da busca oficial do Falcão antes de repetir a
   verificação real e delimitada de sentença/acórdão para `JUR-02`.
8. Vincular `PJE-04` aos endpoints de documentos TRT12 revisados e executar um
   ensaio fechado de download autorizado.
9. Montar a amostra autorizada de 20 processos e designar o revisor, congelar
   os inventários pseudonimizados, pontuar os 15 casos de desenvolvimento em
   `VAL-02` e manter os cinco casos reservados sem pontuação até `VAL-03`.

Esta sequência coloca arquitetura, segurança e medição objetiva antes do
processamento de processos reais.
