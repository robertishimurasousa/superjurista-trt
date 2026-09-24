# Contrato de execução do SuperJurista

Este diretório contém a interface de execução independente do ambiente,
compartilhada por Claude Code e Codex. Os adaptadores podem traduzir descoberta
de instruções, caminhos de habilidades, despacho de tarefas, progresso e nomes
de ferramentas. Não podem modificar regras jurídicas, perfis de tribunais,
esquemas de artefatos nem controles determinísticos.

## Organização

```text
runtime/
├── data-hygiene-contract.json
├── python-contract.json
├── adapters/
│   ├── claude.json
│   └── codex.json
├── contracts/
│   ├── catalog.json
│   ├── README.md
│   ├── VERSIONING.md
│   └── schemas/
│       └── *.v1.schema.json
├── domain/
│   ├── labor-claim-taxonomy.json
│   ├── labor-document-classification.json
│   └── README.md
├── operations/
│   ├── codex-pilot-result.v1.schema.json
│   ├── pilot-preflight.v1.schema.json
│   ├── pilot-preflight.v2.schema.json
│   ├── pilot-preflight.v3.schema.json
│   └── pilot-preflight.v4.schema.json
├── profiles/
│   ├── schema.json
│   ├── registry.json
│   └── trt12.json
├── providers/
│   ├── har-map-review-contract.json
│   ├── har-sanitization-contract.json
│   ├── interfaces.json
│   ├── pje-session-contract.json
│   ├── pje-task-discovery-contract.json
│   └── README.md
└── pipelines/
    ├── calculation-review.v1.schema.json
    ├── conditional-work-plan.v1.schema.json
    ├── conditional-work-results.v1.schema.json
    ├── evidence-review.v1.schema.json
    ├── execution-state.v1.schema.json
    ├── smoke.json
    └── trt12-first-instance.json
```

O manifesto de teste básico descreve um artefato e um controle
compartilhados. O adaptador identifica os vínculos do ambiente.
`scripts/verify_runtime_contract.py` valida os dois contratos e entrega a
validação do artefato ao mecanismo determinístico existente.

## Validar os contratos dos adaptadores

```bash
python3 scripts/verify_runtime_contract.py \
  --runtime claude \
  --manifest runtime/pipelines/smoke.json \
  --validate-only

python3 scripts/verify_runtime_contract.py \
  --runtime codex \
  --manifest runtime/pipelines/smoke.json \
  --validate-only
```

## Executar o controle básico compartilhado

O nome do espaço de trabalho ou `--id` deve fornecer o identificador do
artefato. O arquivo esperado é `<ID>-runtime-smoke.md`.

```bash
python3 scripts/verify_runtime_contract.py \
  --runtime claude \
  --manifest runtime/pipelines/smoke.json \
  --workspace /path/to/workspace

python3 scripts/verify_runtime_contract.py \
  --runtime codex \
  --manifest runtime/pipelines/smoke.json \
  --workspace /path/to/workspace
```

Os dois comandos devem retornar o mesmo resultado de controle para o mesmo
artefato. A meta é equivalência contratual, não textos idênticos em bytes.

## Resolver o pipeline do primeiro grau do TRT12

O manifesto do primeiro grau é a referência compartilhada para etapas,
dependências, limite de tentativas, caminhos dos artefatos, condições,
controles e vínculos opcionais de agentes. Os adaptadores acrescentam somente
instruções, habilidades, despacho, progresso e ferramentas. A etapa
`prepare-triage-input` prepara a entrada protegida dos agentes a partir do
relatório estruturado e da matriz coerentes. `narrate-record` vincula o relator
herdado adaptado, cuja narrativa deve passar pelo controle de cobertura antes
de `route-claims` vincular o triador TRT12. O resolvedor confere se as
instruções existem no repositório e inclui seus resumos SHA-256 no contrato
compartilhado. O ensaio sintético usa uma narrativa congelada; o resolvedor e
o ensaio não invocam Claude Code nem Codex para redigi-la.

`analyze-claims` vincula o analisador trabalhista herdado adaptado.
No ensaio documental fictício, `scripts/run_codex_claim_analysis_stage.py`
envia os sete insumos atuais ao Codex somente depois de conferir a origem
sintética, a revisão derivada do PDF e a ordem de retomada. A análise aceita
e seu recibo privado não representam revisão jurídica; autos reais não são
aceitos por esse despachante.
`draft-judgment` vincula a variante TRT12 do fundamentador para produzir
somente `disposition-matrix.json`; o texto de `judgment-draft.md` vem do
renderizador determinístico existente. `scripts/run_draft_judgment_stage.py`
exige a análise aceita e publica ambos os arquivos apenas se o controle de
congruência passar. Esses vínculos não despacham o modelo por si sós nem
dispensam a revisão jurídica da minuta.
O ensaio `scripts/run_codex_draft_rehearsal.py` despacha apenas a amostra
fictícia com análise anterior conferida; `scripts/import_codex_draft_rehearsal.py`
pode vinculá-la ao checkpoint Codex sintético após verificar os resumos e os
insumos atuais. Esse caminho não aceita os artefatos variáveis de autos reais.
`scripts/run_merge_judgment_stage.py` copia literalmente a minuta aceita
para o arquivo por processo e registra o checkpoint seguinte. O arquivo
fundido continua sujeito a `review-and-gate`; pedido pendente não pode passar
pelo controle final.
No caminho documental fictício, `scripts/run_codex_draft_stage.py` despacha
o fundamentador com a análise atual aceita, confere o recibo da etapa anterior
e registra um novo recibo privado antes de aceitar `draft-judgment`. Esse
despachante não aceita autos reais nem autoriza comando decisório quando a
análise ainda exige revisão humana.

```bash
python3 scripts/resolve_runtime_pipeline.py \
  --runtime claude \
  --manifest runtime/pipelines/trt12-first-instance.json

python3 scripts/resolve_runtime_pipeline.py \
  --runtime codex \
  --manifest runtime/pipelines/trt12-first-instance.json
```

Cada comando imprime um plano de execução resolvido com:

- vínculos do adaptador do ambiente;
- contrato compartilhado normalizado;
- resumo SHA-256 desse contrato.

Resumo e contrato devem ser idênticos em Claude Code e Codex. O resolvedor
bloqueia dependências desconhecidas ou cíclicas, artefatos duplicados,
controles desconhecidos, condições não suportadas, política inválida de
tentativas, instruções de agente ausentes ou fora do diretório permitido e
campos específicos de um ambiente no manifesto compartilhado.

## Retomar o pipeline interrompido com segurança

`scripts/resumable_pipeline.py` implementa o checkpoint neutro usado nos
planos de Claude Code e Codex. `new_execution_state()` cria o estado
versionado; `record_stage_acceptance()` registra uma etapa somente após
aprovar dependências, saídas declaradas, limite de tentativas e controle
determinístico vigente; `plan_resume()` identifica a próxima etapa e eventual
agente vinculado. O adaptador fornece o despacho; o planejador não invoca o
agente nem prepara a entrada do processo.

Um checkpoint só pode ser reutilizado se ainda corresponderem:

- resumo do contrato do pipeline;
- resumo das instruções do agente vinculado, dentro do contrato;
- impressão digital da fonte autorizada;
- impressões digitais agregadas das dependências;
- resumo SHA-256 de cada saída declarada;
- controle de conteúdo vigente da etapa.

Alterar qualquer item torna a etapa pendente e impede reutilizar as etapas
dependentes. O estado é salvo atomicamente conforme
`execution-state.v1.schema.json` e omite de propósito os detalhes de despacho,
permitindo retomar o mesmo checkpoint aceito em Claude Code ou Codex com o
vínculo próprio de cada adaptador.

```bash
python3 -m unittest tests.test_resumable_pipeline -v
```

O módulo planeja e registra a execução; não pratica atos externos, escrita no
PJe, protocolo, assinatura ou publicação.

`scripts/trt12_handoff_gate.py` fornece o validador de conteúdo para
`prepare-triage-input`, `narrate-record` e `route-claims`. Ele recompõe a
entrada a partir do relatório e da matriz atuais, verifica a narrativa pelo
formato e pela cobertura de eventos, pedidos e defesas, e importa a triagem
herdada para conferir a rota por pedido, exigindo correspondência com
`issue-route.json` e fontes vazias até a
integração oficial. Também recusa vínculos simbólicos nos insumos. Qualquer
outra etapa é
recusada por esse validador: o executor do pipeline completo ainda precisa
fornecer os demais controles, sem presumir aprovação. O mecanismo genérico de
checkpoint também recusa saídas por vínculo simbólico, mesmo quando o destino
permanece dentro do espaço de trabalho. O teste sintético exercita aceite e
retomada dos checkpoints de entrada e narrativa e aceite da triagem, mas não
executa um agente de modelo.

`scripts/trt12_initial_gate.py` começa a integrar o mesmo mecanismo de
checkpoint ao manifesto completo: `prepare-profile` só é aceito se
`case-context.json` corresponder ao primeiro grau do TRT12, o número CNJ
pertencer ao ramo e à região corretos e `execution-manifest.json` reproduzir
exatamente o plano resolvido do ambiente. Casos sigilosos sem modo configurado
e caminhos de manifesto que escapem do espaço de trabalho são recusados. O
teste registra e retoma essa etapa no grafo de doze estágios; ainda não valida
etapas posteriores por si só.

`scripts/verify_pje_acquisition_custody.py` confere o índice produzido pelo
adaptador PJe contra todos os bytes adquiridos: identidade do processo,
ausência de lacunas, documentos efetivamente baixados, IDs exclusivos,
tamanhos e SHA-256 exatos. `scripts/trt12_acquisition_gate.py` usa essa
verificação com o estado de recuperação já existente do fork, guardado em
`source-manifest.json`, e com os arquivos canônicos `DOC-*.bin` em um
diretório protegido do espaço de trabalho. O resumo do escopo de autorização
deve vir de uma verificação independente; o próprio arquivo de recuperação
não pode se autoautorizar. Um ensaio sintético registra e retoma
`prepare-profile` e `acquire-case` no manifesto completo. O manifesto curto da
amostra anterior não satisfaz esse controle, e nenhuma captura real do PJe ou
autorização jurídica é inferida desse teste.

`scripts/trt12_extraction_gate.py` acrescenta o controle de `extract-record`.
Ele exige aquisição completa, classificação de cada documento do índice,
linha do tempo sem documentos ausentes ou duplicados e relatório vinculado ao
contexto e aos eventos atuais. Classificações desconhecidas ou conflitantes
continuam explícitas como lacunas; não são convertidas em tipos presumidos.
Um ensaio sintético registra e retoma os três primeiros checkpoints do
manifesto completo. O ensaio não comprova extração de autos reais nem
adequação jurídica.

`scripts/trt12_decision_units_gate.py` confere que a matriz de pedidos cobre
exatamente as posições do relatório, preserva texto e localizadores, mantém
defesas ligadas a reclamados identificáveis e segue as lacunas e os remédios
da taxonomia atual. A matriz de provas deve apontar somente para pedidos e
documentos conhecidos, declarar os pedidos sem prova associada e manter
conflitos simétricos e explícitos. `scripts/trt12_pipeline_gates.py` reúne
os controles implementados sem aceitar etapas posteriores por omissão. O
ensaio automatizado retoma os cinco primeiros checkpoints, incluindo a entrada
protegida do triador, e aponta para `narrate-record`. Em 24/09/2026, um ensaio
local separado executou de fato o relator e o triador Codex sobre a mesma
amostra sintética e registrou sete checkpoints consecutivos no manifesto
completo; a próxima etapa foi `execute-conditional-tracks`. Isso valida
despacho, estrutura e custódia sintéticos, não a veracidade de proposições
probatórias ou a interpretação jurídica.

`scripts/run_codex_narrator.py` acrescenta um despacho **opt-in** apenas para
o relator TRT12 no Codex, atualmente limitado à amostra sintética versionada.
Ele exige `labor-report.json`, `claim-matrix.json`
e `triage-input.md` coerentes em um diretório externo ao repositório, recusa
vínculos simbólicos e saída preexistente, fornece os insumos ao `codex exec`
pela entrada padrão, inicia o comando em diretório temporário vazio e usa
sandbox de leitura e sessão efêmera. A resposta
completa do modelo só é gravada como `report-narrative.md` após o validador de
formato e cobertura aprová-la; falha ou resposta inválida não produz arquivo.
Prepare um diretório novo e privado. O preparador grava somente relatório,
matriz e entrada derivados da amostra sintética versionada, com permissão
`0600`, sem sobrescrever nada. O sinalizador de despacho só funciona quando
relatório e matriz continuam idênticos a essa amostra:

```bash
CODEX_AGENT_REHEARSAL=$(mktemp -d /tmp/superjurista-agentes.XXXXXX)
python3 scripts/prepare_codex_agent_rehearsal.py \
  --workspace "$CODEX_AGENT_REHEARSAL"
python3 scripts/run_codex_narrator.py \
  --workspace "$CODEX_AGENT_REHEARSAL" \
  --synthetic-rehearsal
```

Sem o sinalizador, o despacho direto é recusado antes de chamar o modelo.
Também é recusado se o sinalizador for usado com dados diferentes da amostra.
Os comandos diretos continuam restritos à amostra sintética; não aceitam autos
reais sem passar pelo orquestrador do piloto.

`scripts/prepare_codex_pilot_handoff.py` valida a verificação prévia v4
contra o checkout limpo de `development`, o mapa revisado e os insumos do
mesmo processo. Exige diretórios privados e saída vazia, depois copia apenas
relatório, matriz e entrada de triagem com permissão `0600`. A preparação não
chama o Codex nem libera os comandos diretos de relator e triador para autos
reais. O contrato v4 exige que o provedor do modelo conste explicitamente
no escopo autorizado.

`scripts/run_codex_pilot.py` integra essa preparação aos agentes herdados:
confere GO, provedor Codex, identidade e custódia antes do primeiro prompt;
verifica validade, checkout e integridade dos insumos antes e depois de cada
despacho; e aplica os três controles de transferência. Falhas deixam as
saídas parciais protegidas para revisão, sem sobrescrita nem ato judicial.
O modelo exato vem de `codex_model_id` no registro protegido e é passado
explicitamente ao CLI. Após os controles, `pilot-run-summary.json` registra
somente metadados e SHA-256 dos sete artefatos, com estado
`pending_legal_review` e permissão `0600`; não certifica correção jurídica.
`scripts/verify_codex_pilot_result.py` relê esse conjunto sem chamar o
modelo, confere a autorização histórica, os sete hashes e os três controles
de transferência. Ele recusa arquivo alterado, vínculo simbólico e divergência
de modelo ou processo; um resultado íntegro continua pendente de revisão
jurídica, pois hashes não atestam a verdade das afirmações dos autos.
Até agora esse caminho foi exercitado somente com respostas simuladas dos
modelos; não há GO real nem revisão jurídica que permita despachar o processo
fornecido pelo usuário.

O teste automatizado substitui a chamada externa por uma resposta controlada;
ele **não** comprova uma narrativa realmente gerada pelo Codex. O ensaio local
separado, descrito acima, comprova apenas a execução sobre dados sintéticos.
O validador
confere cobertura e custódia estrutural, não a fidelidade jurídica do texto.
Não há acesso ao PJe nem autorização de uso judicial nesta rotina.

`scripts/run_codex_triager.py` acrescenta o despacho opt-in do triador
herdado. Ele exige a narrativa anterior validada e a entrada protegida atual,
executa o Codex no mesmo isolamento de leitura e aceita somente o Markdown de
triagem que passe pelo controle C2 e pelo importador por pedido. O orquestrador
produz `fontes-triagem.json` vazio e deriva `issue-route.json`; o modelo não
fornece esses dois artefatos diretamente. As três saídas só são publicadas
depois da validação, sem sobrescrever arquivos existentes:

```bash
python3 scripts/run_codex_triager.py \
  --workspace "$CODEX_AGENT_REHEARSAL" \
  --synthetic-rehearsal
```

O mesmo bloqueio sintético vale para o triador. O ensaio anterior com oito
pedidos foi uma execução pontual antes desse bloqueio, não uma autorização
para repetir o comando com qualquer conjunto de autos.

O teste usa uma resposta controlada, não executa o modelo e não comprova
adequação jurídica. Uma execução que devolva resposta inválida ou falhe não
avança o checkpoint. O operador ainda deve registrar separadamente o aceite
das etapas no mecanismo de retomada e submeter a interpretação jurídica à
revisão qualificada.

## Despachar somente as trilhas encaminhadas por pedido

`scripts/build_conditional_work_plan.py` converte o artefato `issue-route`
aceito em `conditional-work-plan` versionado. Cada sinalizador habilitado de
pesquisa jurídica, análise probatória, cálculo ou revisão processual gera uma
tarefa estável vinculada ao pedido. Trilhas desabilitadas não entram no
despacho.

O pedido com abstenção explícita permanece no plano com seus motivos, sem
despacho. Pedido encaminhado sem tarefa, trilha repetida, perguntas divergentes
ou ID de tarefa ligado a outro pedido bloqueiam o fluxo.

```bash
python3 -m unittest tests.test_conditional_work_plan -v
```

Esta camada controla qual trabalho pode executar. Não decide a rota correta de
um pedido real nem substitui a revisão humana e a calibração de `DOM-05`.

`scripts/validate_conditional_work_results.py` exige um recibo por `WRK-*`
encaminhado, com referência a precedentes, provas ou documentos conhecidos,
ou uma lacuna motivada. Resultados de trilhas desabilitadas e referências
órfãs são recusados. `scripts/trt12_conditional_tracks_gate.py` cruza esses
recibos com a rota por pedido e os estados versionados de revisão probatória
e de critérios de cálculo. O manifesto inclui o recibo entre as saídas
assinadas do checkpoint. Uma abstenção integral passa como etapa sem trabalho,
com corpus vazio e revisões `not_required`; não dispara pesquisa fictícia.

O ensaio sintético com revisão pendente alcança o décimo primeiro checkpoint
e aponta para `review-and-gate`. Uma variação sintética com abstenção explícita
alcança os doze checkpoints técnicos, sem comando dispositivo.
`scripts/trt12_claim_analysis_gate.py` reaproveita o controle da etapa anterior,
exige uma análise por pedido e confere vínculos de provas e precedentes com
as respectivas trilhas. Fatos afirmados exigem revisão probatória; resultado
de mérito exige revisão probatória concluída, eventual revisão de cálculo e
recibos vinculados, sem lacunas de mapeamento do pedido. Uma conclusão
processual exige trilha processual vinculada. Enquanto essas condições não
existem, a análise permanece em revisão ou abstenção explícita. O arquivo
da amostra foi corrigido para não afirmar fato com prova ainda pendente.

Esses controles verificam coerência estrutural e custódia, não a verdade dos
fatos, a interpretação dos precedentes nem a correção jurídica do resultado.
`linked` não equivale a revisão jurídica ou probatória concluída.
`scripts/trt12_draft_gate.py` reutiliza a análise aceita e os controles
herdados de congruência e renderização. O dispositivo de um pedido pendente
ou abstido não pode conter comando operativo, período ou efeitos; a minuta
deve coincidir exatamente com a renderização dos artefatos estruturados,
sem frases adicionais. O ensaio sintético passou a aplicar o mesmo controle
antes de publicar saídas. `scripts/trt12_merge_gate.py` verifica que o arquivo
por processo contém exatamente os mesmos bytes da minuta aceita e rejeita
vínculos simbólicos. A etapa final ainda precisa distinguir o resultado dos
controles técnicos de uma autorização jurídica: na amostra atual há pedido
`pending_human_review`, mesmo quando o relatório técnico de citações e
cálculos indica `passed`. `scripts/trt12_final_gate.py` recompõe o relatório,
confere excertos e estados de cálculo com os artefatos de origem e recusa
o checkpoint final enquanto qualquer pedido estiver nessa condição. A
abstenção explícita pode encerrar o fluxo técnico sem produzir sentença de
mérito. Nenhum desses checkpoints substitui revisão jurídica qualificada
nem autoriza uso do resultado como sentença em processo real.

## Validar o perfil do tribunal TRT12

O esquema do perfil é independente do ambiente. Valores do tribunal ficam em
`trt12.json`; vínculos de provedores e fontes oficiais ficam no registro
versionado. Um vínculo declarado registra o contrato esperado de futuros
adaptadores, sem afirmar implementação ou verificação operacional.

```bash
python3 scripts/validate_tribunal_profile.py \
  --schema runtime/profiles/schema.json \
  --registry runtime/profiles/registry.json \
  --profile runtime/profiles/trt12.json
```

O comando bloqueia divergência estrutural, dígito desconhecido de ramo CNJ,
grau habilitado sem adaptador processual compatível, fonte ou adaptador de
pesquisa não registrado, conjunto vazio de assinaturas ou política de MVP que
permita protocolo ou assinatura externa. Somente o primeiro grau está ativo
para TRT12; publicação também é proibida e o contrato do segundo grau está
presente, mas desabilitado.

## Validar os contratos dos artefatos jurídicos

O catálogo abrange contexto processual, classificação documental, linha do
tempo, relatório trabalhista, matriz de pedidos, matriz de provas, rotas,
corpus de precedentes, análise dos pedidos e matriz do dispositivo. Cada
esquema possui dados de teste positivos e negativos independentes.

```bash
python3 scripts/validate_artifact_contracts.py \
  --catalog runtime/contracts/catalog.json \
  --fixtures-root tests/fixtures/contracts
```

Use `--contract <id> --document <path>` em vez de `--fixtures-root` para
validar um artefato gerado. Versões e contratos desconhecidos bloqueiam. As
regras de migração estão em `runtime/contracts/VERSIONING.md`.

## Classificar documentos trabalhistas com a base sintética

O classificador determinístico consome rótulos normalizados do provedor,
títulos ou trechos locais de texto e emite apenas IDs estáveis dos documentos,
valores da taxonomia, IDs das regras e estado. Não copia o texto-fonte ao
artefato e preserva `unknown` ou `conflict` em vez de adivinhar.
O contrato vigente é v2: certidões e comunicações processuais são categorias
distintas de despachos e decisões; o classificador só considera metadados para
essas duas regras. A migração protegida de resultados v1 está descrita em
`runtime/contracts/README.md` e não reinterpreta os autos.

```bash
python3 -m unittest tests.test_labor_document_classifier -v
```

Isso comprova a base versionada e o contrato de saída, não a acurácia
calibrada em autos do TRT12. A calibração exige amostra autorizada e aprovada.

## Montar linha do tempo e relatório trabalhista vinculados às fontes

`scripts/build_procedural_timeline.py` converte segmentos classificados do PDF
do PJe em um evento datado e vinculado à fonte por documento. Classificações
desconhecidas ou conflitantes permanecem lacunas explícitas. A CLI rejeita
saída dentro do repositório e arquivos já existentes, gravando o artefato
protegido com acesso exclusivo do titular.

```bash
python3 scripts/build_procedural_timeline.py \
  --segments /protected/input/document-segments.json \
  --classification /protected/input/document-classification.json \
  --output /protected/output
```

O montador do relatório recebe candidatos estruturados após a classificação e
emite JSON determinístico de partes, fase, eventos, pedidos, defesas e lacunas.
Cada item afirmado preserva documento e localizador de origem; informações
desconhecidas ou ausentes nunca são completadas silenciosamente.

`scripts/extract_pje_labor_report.py` conecta PDF protegido, mapa de segmentos,
classificação e linha do tempo ao montador. Tribunal, grau e sigilo são
entradas explícitas para manter o núcleo portável. O extrator confere resumo
e páginas do PDF, exige custódia documental correspondente, preserva
localizadores e examina a petição inicial classificada inteira por meio de
`scripts/extract_labor_positions.py`. Somente títulos explícitos de seções de
pedidos viram posições; menções no corpo são ignoradas, títulos quebrados são
reconstituídos, rótulos suportados mantêm a taxonomia e categorias sem suporte
recebem `unmapped_` para revisão humana. `scripts/extract_labor_defenses.py`
aplica o mesmo limite de títulos a cada contestação classificada. Grupos de
posições defensivas conservam a custódia do documento e IDs distintos; a
ausência de resposta não é inferida. A lacuna do relatório v1 é global por
tipo de posição; cobertura da defesa por pedido cabe à matriz de pedidos.

```bash
python3 scripts/extract_pje_labor_report.py \
  --input /protected/process.pdf \
  --segments /protected/input/document-segments.json \
  --classification /protected/input/document-classification.json \
  --timeline /protected/input/procedural-timeline.json \
  --output /protected/output \
  --tribunal TRT12 \
  --instance 1 \
  --confidentiality public_or_authorized
```

```bash
python3 -m unittest \
  tests.test_procedural_timeline_builder \
  tests.test_labor_report_builder \
  tests.test_labor_position_extraction \
  tests.test_labor_defense_extraction \
  tests.test_pje_labor_report_extraction \
  -v
```

Isso estabelece o limite determinístico de `DOM-02` para linha do tempo,
contexto, partes e relatório. Vínculo de reclamados por pedido, calibração com
vários processos e revisão cega de amostra TRT12 aprovada continuam sendo
evidências de aceite separadas.

## Montar matriz de pedidos e providências requeridas

`runtime/domain/labor-claim-taxonomy.json` define rótulos de base versionados
e providências compatíveis. `scripts/build_claim_matrix.py` recebe candidatos
estruturados de pedidos e defesas, preserva posições de vários reclamados e
emite entradas vinculadas às fontes pelo contrato `claim-matrix`. Rótulos e
providências sem suporte permanecem lacunas visíveis para revisão.

```bash
python3 -m unittest tests.test_claim_matrix_builder -v
```

A taxonomia é uma base sintética de engenharia. Sensibilidade e cobertura de
categorias não são aceitas antes da calibração em amostra TRT12 aprovada.

## Montar matriz de provas vinculadas aos pedidos

`scripts/build_evidence_matrix.py` monta candidatos de prova conforme os
manifestos conhecidos de pedidos e documentos. Preserva localizadores e
limitações, registra se cada item apoia, contraria ou contextualiza um pedido,
normaliza vínculos de contradição simetricamente e informa pedidos sem provas
vinculadas.

```bash
python3 -m unittest tests.test_evidence_matrix_builder -v
```

Essa interface sintética não avalia o peso da prova nem comprova completude em
processos TRT12 reais. Essas conclusões exigem calibração autorizada e revisão
humana.

## Montar encaminhamentos por pedido

`scripts/build_issue_routes.py` exige exatamente uma rota candidata por pedido
conhecido. Trilhas jurídicas e probatórias habilitadas exigem perguntas
concretas; cálculo e revisão processual são valores booleanos explícitos com
justificativa geral. Se nenhuma trilha puder ser escolhida, a rota fica
`abstained` com um ou mais motivos; omissão silenciosa é rejeitada.

```bash
python3 -m unittest tests.test_issue_router -v
```

O montador valida cobertura e coerência interna. Não determina a rota
juridicamente correta de pedido TRT12 real sem fontes aprovadas e revisão humana.

## Montar decisões por pedido e minuta para revisão

`scripts/build_claim_decisions.py` monta uma análise e um dispositivo vinculado
por pedido conhecido e gera minuta Markdown determinística. Resultados de
mérito exigem fatos, IDs de prova, avaliação probatória, normas aplicáveis e
fundamentação. Resultados processuais exigem fatos e normas. Análises
pendentes ou com abstenção devem preservar limitação explícita.

```bash
python3 -m unittest tests.test_claim_decision_builder -v
```

A minuta é artefato estruturado para revisão, não ato judicial pronto para
assinatura ou publicação. Correção jurídica, estilo do gabinete, critérios de
cálculo e texto do dispositivo para TRT12 real exigem dados autorizados e
revisão humana.

## Verificar conformidade das interfaces dos provedores

O manifesto define capacidades de obtenção de processos no PJe e pesquisa
jurídica em fontes oficiais. Implementações concretas devem obedecer às
requisições e respostas tipadas e aos executores determinísticos de
`scripts/provider_interfaces.py`.

```bash
python3 -m unittest tests.test_provider_interfaces -v
```

A suíte sintética usa código de tribunal não alvo e cobre fluxos completos com
provedores simulados, capacidades ausentes, cursores repetidos, divergências
de resumos de downloads e fontes oficiais sem HTTPS. Sua aprovação comprova
apenas conformidade da interface, não acesso real ao PJe ou a provedores de
pesquisa.

O classificador de sessões é uma camada separada e neutra quanto ao provedor.
Consome apenas estado sanitizado, marcadores e nomes de cookies e cabeçalhos;
bloqueia contradições ou evidência ausente:

```bash
python3 -m unittest tests.test_pje_session_adapter -v
```

Esse teste não autentica. O vínculo do classificador ao TRT12 ainda depende
de mapa de endpoints autorizado e revisado.

A descoberta de tarefas e processos usa a mesma interface: adaptadores
normalizam respostas dos provedores; o executor compartilhado verifica
paginação completa, IDs estáveis, região CNJ e saída determinística sem segredos:

```bash
python3 -m unittest tests.test_pje_task_discovery -v
```

O teste sintético não comprova endpoint nem nome de tarefa do TRT12.

Capturas HAR autorizadas do PJe podem ser reduzidas a mapa determinístico de
endpoints sem segredos por `scripts/sanitize_pje_har.py`. O HAR bruto deve
ficar fora do repositório. Consulte `runtime/providers/README.md` para o
comando e o controle separado de revisão do mapa.

## Validar o contrato de Python

Os scripts centrais aceitam Python 3.9+. Servidores MCP locais usam o SDK MCP
1.x e exigem Python 3.10+.

```bash
python3 scripts/check_python_contract.py \
  --root . \
  --contract runtime/python-contract.json \
  --mode core

python3 scripts/check_python_contract.py \
  --root . \
  --contract runtime/python-contract.json \
  --mode mcp
```

O validador também rejeita referências ambíguas a `python` ou comando direto
`pip` na documentação executável e nos arquivos-fonte do scaffold.

## Validar a proteção dos dados

O contrato de proteção dos dados define regras de exclusão do Git, caminhos
sensíveis proibidos, exceções para dados sanitizados de teste, detectores de
conteúdo e tamanho máximo dos arquivos examináveis.

```bash
python3 scripts/check_data_hygiene.py \
  --root . \
  --contract runtime/data-hygiene-contract.json
```

O verificador lê apenas arquivos versionados e candidatos a commit não
ignorados. Nunca imprime o valor de credencial encontrada.
