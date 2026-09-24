# Contratos do domínio trabalhista

Este diretório contém regras da Justiça do Trabalho compartilhadas por Claude Code e Codex,
independentes do ambiente de execução. São referências determinísticas iniciais, não
afirmações de acerto jurídico calibrado.

## Classificação de documentos

`labor-document-classification.json` define a taxonomia versionada de documentos e as
regras auditáveis de expressões usadas por `scripts/classify_labor_documents.py`. O
classificador normaliza caixa, acentos e pontuação, prioriza regras específicas e
retorna `unknown` ou `conflict` quando as evidências são insuficientes ou contraditórias.
Na versão 2, certidões e comunicações processuais têm tipos próprios e eventos
neutros na linha do tempo; suas regras consultam somente tipo do provedor e título,
não trechos livres dos autos. Uma classificação histórica v1 não é recalculada
automaticamente: a migração preserva os tipos e `unknown` originais.

A saída contém apenas identificadores estáveis dos documentos e evidências da
classificação. Metadados do provedor, trechos dos documentos, nomes das partes e
conteúdo do processo não são copiados para o resultado.

```bash
python3 -m unittest tests.test_labor_document_classifier -v
```

Os testes sintéticos demonstram comportamento determinístico. DOM-01 permanece
incompleto até que a taxonomia seja calibrada e revisada com um conjunto de casos
TRT12 aprovado e autorizado.

## Linha do tempo processual e relatório trabalhista

`scripts/build_procedural_timeline.py` converte segmentos classificados de PDFs do
PJe no artefato versionado `procedural-timeline`. Produz um evento datado e vinculado
à fonte por segmento, distingue classificação desconhecida de conflito de
classificação e grava artefatos protegidos apenas fora do repositório.
Resumos e localizadores emitidos por esse gerador são escritos em português.
O diretório de saída deve existir, ter permissão `0700` e não ser vínculo
simbólico. As mensagens próprias do comando estão em português; os códigos de
estado JSON permanecem estáveis.
Os extratores de pedidos, defesas, qualificações e providências também emitem
resumos ou localizadores em português; a leitura da matriz aceita localizadores
antigos em inglês sem reescrever sua origem. Códigos técnicos, trechos literais
dos autos e artefatos históricos não são traduzidos automaticamente.

`scripts/build_labor_report.py` converte candidatos estruturados já extraídos no
artefato versionado `labor-report`. Partes, fase processual, eventos, pedidos e
defesas mantêm os identificadores dos documentos e os localizadores das fontes.
Os identificadores estáveis e as referências ao manifesto são validados; a ordem
de saída é determinística; a ausência de informação vira lacuna explícita de
revisão, não fato presumido.

`scripts/extract_pje_labor_report.py` extrai o contexto do processo, todas as
partes qualificadas na petição inicial e a fase de conhecimento de um PDF do PJe
com origem rastreável. Concilia as partes principais dos metadados do PJe com a
petição inicial, obtém a unidade judiciária de documento processual classificado,
consome toda a linha do tempo e usa `scripts/extract_labor_positions.py` para
reconhecer títulos explícitos de seções de pedidos em toda a inicial classificada.
Identificadores de posições não dependem da ordem das páginas; cada ocorrência
mantém a página de origem; menções em prosa são ignoradas; categorias sem suporte
permanecem visíveis com rótulos `unmapped_`. `scripts/extract_labor_defenses.py`
percorre todos os documentos classificados como defesa sob a mesma regra de
título exato, atribui uma faixa distinta de identificadores a cada documento e
emite apenas posições da parte ré efetivamente encontradas. O relatório não
inventa resposta para pedido sem seção de defesa correspondente.

```bash
python3 -m unittest \
  tests.test_procedural_timeline_builder \
  tests.test_labor_report_builder \
  tests.test_labor_position_extraction \
  tests.test_labor_defense_extraction \
  tests.test_pje_labor_report_extraction \
  -v
```

O conjunto sintético verifica a origem do PDF, a conciliação das partes, as fontes
da linha do tempo, a saída protegida, a extração por títulos exatos de pedidos e
defesas, a separação de múltiplas defesas e a montagem determinística do relatório.
DOM-02 ainda exige revisão cega de vários casos TRT12 aprovados e autorizados.
A indicação de defesa ausente por pedido pertence a DOM-03: a versão 1 do
`labor-report` registra lacunas apenas por tipo geral de posição.

## Taxonomia de pedidos e providências requeridas

`labor-claim-taxonomy.json` define rótulos iniciais de pedidos e providências
compatíveis com cada rótulo. `scripts/build_claim_matrix.py` valida candidatos
estruturados, mantém as posições da parte autora e da parte ré vinculadas
separadamente às fontes, aceita múltiplas defesas e preserva rótulos ou
providências sem suporte como lacunas, sem reclassificá-los silenciosamente.

`scripts/extract_pje_claim_matrix.py` conecta o relatório trabalhista protegido
e o manifesto de segmentos do PDF original a esse gerador. Verifica o resumo
criptográfico do PDF, o número de páginas, o número do processo e o intervalo
de páginas de cada posição. Cada documento de defesa deve estar associado
explicitamente a uma parte ré; o rótulo deve corresponder exatamente, e defesas
ambíguas ou sem pedido vinculado são rejeitadas. Sem `--extract-remedies`, as
providências requeridas ficam vazias e suas lacunas são explícitas. Com essa
opção, `scripts/extract_labor_remedies.py` lê a seção final de pedidos, vincula
itens identificados por letras e subitens numerados aos pedidos do relatório e
registra páginas e trechos exatos da fonte em um
`requested-remedy-evidence.json` protegido e separado. Na versão 2, itens por
letra não reconhecidos conservam ID, documento, página e trecho extraído em
`unmatched_items`, além de `unmatched_item_ids`; não recebem pedido ou
providência presumidos. Subitens numerados ambíguos são rejeitados.
Alternativas condicionais são marcadas para revisão humana.
Códigos de providência sem suporte permanecem na matriz com lacuna explícita da
taxonomia, sem serem forçados a uma categoria conhecida. Fatos controvertidos
e questões jurídicas ainda não são extraídos. O diretório de saída deve existir
fora do repositório; ambos os arquivos são criados uma única vez, com permissão
`0600`.

```bash
python3 scripts/extract_pje_claim_matrix.py \
  --input /protected/process.pdf \
  --report /protected/report/labor-report.json \
  --segments /protected/segments/document-segments.json \
  --output /protected/matrix-v2 \
  --defense-party DOC-002=PTY-002 \
  --extract-remedies
python3 -m unittest tests.test_claim_matrix_builder tests.test_labor_remedy_extraction tests.test_pje_claim_matrix_extraction -v
```

DOM-03 permanece incompleto até que a calibração cega demonstre as metas de
recuperação e cobertura final de pedidos do roadmap em casos TRT12 aprovados e
autorizados.

## Entrega ao triador herdado do SuperJurista

`scripts/build_superjurista_triage_input.py` converte `labor-report.json` e
`claim-matrix.json` existentes em uma entrada Markdown com referências às fontes
para o `scaffold/agents/analise/triador-processual.md` herdado. Verifica a
cobertura completa dos pedidos e defesas e a coerência exata das fontes e dos
resumos; não extrai novamente o processo, seleciona uma rota nem executa o
agente. A saída protegida fica fora do repositório e não sobrescreve arquivos.
Consulte
[`spec/inventory/superjurista-flow-convergence.md`](../../spec/inventory/superjurista-flow-convergence.md)
para as etapas de integração de agentes e ambientes de execução ainda pendentes.

A variante TRT12 do triador herdado é
`scaffold/agents/analise/triador-processual-trt12.md`. Seu único bloco C2
acrescenta uma rota candidata por pedido; `scripts/import_superjurista_triage.py`
valida a saída e escreve `issue-route.json` somente se todos os pedidos e a rota
global herdada forem coerentes. A interface de comando também verifica se a
entrada protegida corresponde ao relatório e à matriz atuais e se o agente
repetiu seu SHA-256. Por enquanto, não são aceitas fontes externas de triagem
nem rotas diretas sem comprovação. A execução do agente e a calibração jurídica
continuam pendentes.

```bash
python3 -m unittest tests.test_superjurista_triage_input tests.test_superjurista_triage_routes -v
```

Para revisão independente, `scripts/prepare_claim_blind_review.py` usa apenas o
PDF original e seu mapa de segmentos. Verifica a origem do PDF e cria um
formulário de inventário vazio em português, fora do repositório, com permissão
`0600`. O comando não lê o relatório, a matriz de pedidos nem as evidências de
providências do sistema; também não preenche quantidades, rótulos ou pedidos.
Um revisor qualificado deve ler as páginas-fonte, registrar todos os pedidos
principais e acessórios e congelar o inventário antes de ver a saída do sistema.
Preparar o formulário não conclui a revisão nem melhora as métricas de DOM-03.
Quem já viu os rótulos ou as quantidades do sistema não pode atestar que esse
inventário foi cego; deve-se designar outro revisor qualificado ou registrar a
verificação como retorno não cego. O diretório de saída deve existir fora do
repositório, não ser vínculo simbólico e permitir acesso somente ao operador
(`0700`); o formulário é criado em `0600` e não substitui arquivo existente.

```bash
python3 scripts/prepare_claim_blind_review.py \
  --input /protected/process.pdf \
  --segments /protected/segments/document-segments.json \
  --document-id DOC-001 \
  --case-id PILOT-001 \
  --output /protected/blind-review-v1
python3 -m unittest tests.test_claim_blind_review_packet -v
```

## Montagem da matriz de evidências

`scripts/build_evidence_matrix.py` aplica as regras de rastreabilidade de fontes
do contrato compartilhado `evidence-matrix`. Cada proposição se vincula a um ou
mais pedidos e a um localizador de documento, preserva limitações, declara sua
relação com o pedido e registra conflitos explícitos. Pedidos sem evidência
vinculada aparecem em `uncovered_claim_ids`.

```bash
python3 -m unittest tests.test_evidence_matrix_builder -v
```

DOM-04 permanece incompleto até que cada proposição material e contradição
passe por revisão cega em casos TRT12 aprovados e autorizados.

## Encaminhamento de questões por pedido

`scripts/build_issue_routes.py` monta uma rota para cada pedido conhecido. Cada
rota informa se exige pesquisa jurídica, análise de provas, revisão de cálculo
ou revisão processual e preserva a justificativa e as perguntas específicas do
fluxo. Um pedido sem fluxo habilitado deve registrar motivo explícito de
abstenção; pedidos ausentes, rotas duplicadas e estados contraditórios são
rejeitados.

```bash
python3 -m unittest tests.test_issue_router -v
```

DOM-05 permanece incompleto até que a seleção de rotas e o comportamento de
abstenção passem por revisão cega em casos TRT12 aprovados e autorizados.

## Análise por pedido, dispositivo e montagem da minuta

`scripts/build_claim_decisions.py` mantém cada pedido como unidade decisória
independente. Os identificadores de análise vinculam fatos, evidências, regras,
fundamentação, resultado e limitações a exatamente um item do dispositivo. O
dispositivo herda o resultado analisado, e o gerador determinístico mantém a
ordem dos pedidos e os vínculos das análises visíveis na minuta para revisão.

```bash
python3 -m unittest tests.test_claim_decision_builder -v
```

DOM-06 permanece incompleto até que análises, comandos, períodos, efeitos,
critérios de cálculo e redação passem por revisão jurídica cega em casos TRT12
aprovados.
