# Manual do operador — primeiro grau do TRT12

## Finalidade e limite de segurança

Este manual prepara e verifica o ambiente local do SuperJurista TRT12. Ele
permite somente obtenção, análise e geração local de minutas. Não protocola,
assina, publica, move tarefas no PJe nem pratica outro ato judicial externo.

Use apenas registros cujo acesso esteja autorizado ao operador. Capturas HAR
brutas, sessões, cookies, cabeçalhos, autos, espaços de trabalho gerados e
dados pessoais ou sigilosos devem ficar fora do Git, nos caminhos locais
ignorados indicados abaixo.

Interrompa imediatamente se algum comando expuser credencial, gravar dados
processuais em caminho versionado, relatar divergência de integridade ou
reprovar um controle.

## 1. Começar de checkout limpo

Use a branch `development` aprovada e confirme a ausência de alterações locais:

```bash
git switch development
git pull --ff-only origin development
git status --short --branch
```

Resultado esperado: `development` alinhada a `origin/development`, sem arquivos
alterados ou não rastreados.

## 2. Instalar requisitos do macOS

O ambiente compartilhado exige Python 3.10 ou mais recente. O núcleo isolado
aceita Python 3.9, mas essa versão não executa os servidores MCP locais.

Instale as ferramentas externas de OCR uma única vez:

```bash
brew install tesseract tesseract-lang poppler
tesseract --version
tesseract --list-langs
pdftoppm -v
```

Resultado esperado: Tesseract e Poppler informam suas versões e
`tesseract --list-langs` inclui `por`.

## 3. Criar ambiente Python isolado

Substitua `/path/to/python3.12` pelo executável instalado de Python 3.10+.
Não use o Python 3.9 do sistema macOS para o ambiente combinado.

```bash
/path/to/python3.12 -m venv .venv
source .venv/bin/activate
python3 --version
python3 -m pip install -r requirements/runtime.txt
for requirements_file in scaffold/mcp-servers/*/requirements.txt; do
  python3 -m pip install -r "$requirements_file"
done
```

Resultado esperado: interpretador ativo em Python 3.10 ou superior e todos os
comandos de instalação concluídos. `.venv/` é ignorado pelo Git.

## 4. Comprovar a prontidão do host

Execute os contratos de versão e, depois, o ensaio real de MCP/OCR:

```bash
python3 scripts/check_python_contract.py --root . \
  --contract runtime/python-contract.json --mode core
python3 scripts/check_python_contract.py --root . \
  --contract runtime/python-contract.json --mode mcp
python3 scripts/rehearse_target_host.py --root .
```

O último comando deve informar `"status": "ready"`, cinco servidores MCP,
uma página de OCR e um resumo da evidência. Ter pacotes instalados não basta:
o ensaio importa os cinco servidores e executa o conversor PDF preservado com
Poppler e OCR em português do Tesseract.

## 5. Executar os controles de qualidade e os dois ambientes sintéticos

```bash
python3 scripts/quality_gate.py --root .
python3 -m unittest tests.test_cross_runtime_pipeline -v
```

Crie dois espaços de trabalho novos e vazios e execute os mesmos dados
sanitizados de teste:

```bash
CLAUDE_REHEARSAL=$(mktemp -d /tmp/superjurista-claude.XXXXXX)
CODEX_REHEARSAL=$(mktemp -d /tmp/superjurista-codex.XXXXXX)
python3 scripts/run_synthetic_pipeline.py \
  --runtime claude \
  --fixture tests/fixtures/pipeline/synthetic-first-instance.json \
  --workspace "$CLAUDE_REHEARSAL"
python3 scripts/run_synthetic_pipeline.py \
  --runtime codex \
  --fixture tests/fixtures/pipeline/synthetic-first-instance.json \
  --workspace "$CODEX_REHEARSAL"
```

Os dois resumos devem informar:

- `artifact_count` igual ao total de saídas do manifesto vigente (24 nesta versão);
- `global_gate_status` igual a `passed`;
- o mesmo `contract_digest`;
- o mesmo `shared_artifact_digest`.

Os espaços contêm somente dados sintéticos. Um ensaio aprovado comprova
execução dos ambientes e contratos, não adequação jurídica nem acesso real ao
PJe.

## 6. Preparar uma captura autorizada do TRT12

Não coloque HAR bruto no repositório. Salve-o em local controlado pelo operador,
fora do checkout, e gere apenas o mapa sanitizado:

Durante uma sessão autorizada normal e somente de leitura, guarde o registro de
rede ao abrir a lista de tarefas, localizar um processo não sigiloso do
primeiro grau, abrir a lista de documentos e baixar um documento. Não
protocole, assine, publique, mova tarefas, altere o processo, expire a sessão
nem provoque falha HTTP ou do provedor para ampliar a cobertura da captura.

```bash
python3 scripts/sanitize_pje_har.py \
  --input /path/outside-the-repository/authorized-capture.har \
  --output tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1 \
  --authorized-capture
python3 scripts/validate_pje_har_map.py \
  --map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1
```

Antes de versionar um mapa sanitizado, revise cada endpoint e marcador
preservado. O código de saída `0` indica cobertura técnica suficiente, não
prova de autorização. O código `1` indica cobertura incompleta; `2` indica
mapa inválido ou incoerente, que não pode ser usado. Uma captura normal pode
informar `observed_failure_gaps`: são limitações registradas, não instruções
para provocar erros. Sua resolução exige evidência segura e autorização
separada para sessão e recuperação.

## 7. Tratar material processual real

Guarde material autorizado apenas em caminho local ignorado, como
`processos/`, `cases/`, `data/` ou `workspace/`. Nunca copie documentos
brutos ou estado autenticado do navegador para `tests/`, `runtime/` ou `spec/`.

Antes do primeiro ensaio real, registre:

- operador e alcance da autorização;
- se o processo é público, restrito ou sigiloso;
- requisitos de retenção e exclusão;
- caminho local da entrada e saída fora do Git;
- número do processo apenas no registro local protegido, nunca em dado de
  teste versionado;
- operação delimitada pretendida e condição explícita de parada.

O fluxo real do PJe permanece desabilitado até a revisão do mapa sanitizado.
Após habilitado, sessão expirada, exigência de MFA, resposta não autorizada,
cursor repetido, divergência de catálogo ou resumo e tentativas esgotadas
devem interromper a execução, sem protocolo ou movimentação de tarefas.

Para a revisão **cega** dos pedidos, antes de mostrar ao revisor qualquer
relatório ou matriz extraídos, use o PDF original e seus segmentos já
conferidos para criar um formulário vazio. O destino deve existir fora do Git,
ter permissão `0700` e não ser vínculo simbólico:

```bash
python3 scripts/prepare_claim_blind_review.py \
  --input /protected/path/caso/processo.pdf \
  --segments /protected/path/caso/document-segments.json \
  --document-id DOC-001 \
  --case-id PILOT-001 \
  --output /protected/path/revisao-cega
```

`DOC-001` deve ser substituído pelo documento da petição inicial identificado
nos segmentos; o pseudônimo não deve conter o número CNJ. O revisor deve ler
o PDF e congelar o inventário antes de comparar com a saída do sistema. Quem
já viu os pedidos extraídos não pode atestar independência dessa revisão.

Antes de formar a matriz de provas, o inventariador probatório herdado precisa
de fontes delimitadas por documento. Se o PDF consolidado do PJe e
`claim-matrix.json` do mesmo caso já estiverem no diretório privado externo
ao Git (`0700`), prepare essas entradas localmente:

```bash
python3 scripts/prepare_evidence_inventory_packets.py \
  --workspace /protected/path/caso \
  --pdf /protected/path/caso/processo.pdf
```

O preparador percorre todos os documentos do sumário nativo do PDF, conserva
as alegações da matriz separadas do texto literal e grava um pacote por
documento, os segmentos e `evidence-inventory-index.json` em arquivos `0600`.
Ele recusa páginas sem texto extraível, documentos acima do limite vigente,
fonte divergente e saída preexistente, sem deixar conjunto parcial. Não chama
o inventariador nem produz `evidence-matrix.json`: a associação entre prova e
pedido, a conferência visual e a revisão jurídica continuam pendentes.

A variante `scaffold/agents/analise/inventariador-probatica-trt12.md` define
observações descritivas por documento no contrato
`runtime/pipelines/evidence-inventory-observations.v1.schema.json`. Quando uma
observação estiver disponível em arquivo privado, confira seus trechos e IDs
sem enviar conteúdo a provedor:

```bash
python3 scripts/validate_evidence_inventory_observations.py \
  --result /protected/path/caso/DOC-001-inventory-observations.json \
  --packet /protected/path/caso/DOC-001-inventory-source.md \
  --pdf /protected/path/caso/processo.pdf \
  --segments /protected/path/caso/inventory-pje-pdf-segments.json \
  --matrix /protected/path/caso/claim-matrix.json \
  --document-id DOC-001
```

`[OK]` confirma a identidade do pacote, o documento, os pedidos conhecidos e
os trechos literais nas páginas indicadas. Não comprova que todos os itens
foram encontrados ou que a associação a um pedido está correta. A variante
ainda não tem despacho autorizado com autos reais nem importação automática
para `evidence-matrix.json`; revisão humana continua obrigatória.

Após receber **uma observação por documento** no mesmo diretório privado,
confira o lote inteiro antes de apresentar qualquer inventário do processo:

```bash
python3 scripts/validate_evidence_inventory_batch.py \
  --workspace /protected/path/caso
```

O comando exige exatamente os resultados `DOC-xxx-inventory-observations.json`
dos documentos do PDF, revalida índice, PDF, matriz, segmentos, pacotes e cada
trecho literal, e informa somente contagens. Arquivo faltante ou extra bloqueia
a cobertura técnica. Um resultado `no_item_identified` ou `insufficient`
permanece explicitamente no total, não se converte em prova ou conclusão de
exaustividade. Nenhuma chamada de modelo nem gravação é feita por esse comando.

Para ensaiar a variante com o Codex **sem autos reais**, crie um diretório
externo ao Git, vazio e `0700`, e execute:

```bash
python3 scripts/run_codex_inventory_rehearsal.py \
  --workspace /protected/path/ensaio-inventario \
  --model gpt-6-sol \
  --synthetic-rehearsal
```

O ensaio gera internamente um PDF fictício de dois documentos, usa o despachante
Codex existente com ferramentas desabilitadas e sandbox de leitura, valida
cada resposta e o lote completo antes de publicar arquivos `0600`. Se um
documento falhar, não publica lote parcial. O resumo registra o identificador
de modelo **solicitado**, não comprova o snapshot interno executado. Sucesso
nesse ensaio não autoriza envio de autos reais ao provedor nem substitui
revisão jurídica ou conferência visual da prova.

Para abrir a seleção humana de um lote **já validado** no diretório privado:

```bash
python3 scripts/review_evidence_inventory.py prepare \
  --workspace /protected/path/caso
```

O arquivo `evidence-inventory-review.json` nasce `0600`, com todas as páginas
não conferidas e todas as decisões `pending`. Consulte
[`spec/validation/evidence-inventory-review-guide.md`](../validation/evidence-inventory-review-guide.md)
antes do preenchimento. Para obter um roteiro legível de páginas e itens,
enquanto o registro ainda está intacto:

```bash
python3 scripts/prepare_evidence_inventory_review_packet.py \
  --workspace /protected/path/caso
```

O roteiro `evidence-inventory-review-packet.md` fica no mesmo diretório privado,
sem sobrescrita, e contém trechos dos autos: não o inclua no Git nem o envie
a serviços externos. Ele ajuda a localizar o que conferir no PDF original,
mas não registra decisões; preencha somente o JSON de revisão. A relação com
pedidos, a proposição e a justificativa exigem revisão jurídica qualificada;
a conferência técnica de arquivo e trecho não substitui essa decisão. Depois
de preencher o registro:

```bash
python3 scripts/review_evidence_inventory.py validate \
  --workspace /protected/path/caso
```

O validador reabre o PDF, o índice e todas as observações, exige uma decisão
por item e leitura declarada de todas as páginas. O retorno
`reviewed_for_selection` é apenas consistência técnica de uma declaração de
revisão, não autenticação do revisor nem aprovação de mérito.
`requires_followup` preserva itens adiados, omissões relatadas e inventários
`insufficient`. Nenhum dos comandos cria `evidence-matrix.json`.

Somente com `reviewed_for_selection`, prepare os candidatos a partir da
revisão declarada:

```bash
python3 scripts/build_reviewed_evidence_candidates.py \
  --workspace /protected/path/caso
```

O comando reutiliza `build_evidence_matrix.py`, gera
`evidence-matrix-candidates.json` e `evidence-selection-provenance.json` em
arquivos `0600` e não sobrescreve saídas existentes. A matriz canônica
`evidence-matrix.json` permanece intacta. A seleção é uma declaração do
revisor, não identidade autenticada ou conclusão judicial; conflitos e força
probante continuam para análise posterior.

Antes de usar esses candidatos como insumo de qualquer etapa posterior,
reconfira o conjunto publicado contra o PDF, o inventário e a revisão atuais:

```bash
python3 scripts/verify_reviewed_evidence_candidates.py \
  --workspace /protected/path/caso
```

O verificador é somente leitura, compara integralmente os dois arquivos
publicados com uma reconstrução das fontes e mostra apenas contagens. Uma
alteração posterior na revisão ou nos candidatos exige nova análise; não
edite os arquivos publicados para forçar a conferência. O resultado não
autentica o revisor, não avalia mérito jurídico e não promove os candidatos
para `evidence-matrix.json`.

Quando o PDF consolidado, seus segmentos e a matriz de provas do mesmo caso
já estiverem protegidos e autorizados, é possível preparar apenas as fontes
de um pedido para revisão local, sem chamar modelo:

```bash
python3 scripts/prepare_source_evidence_packet.py \
  --pdf /protected/path/processo.pdf \
  --segments /protected/path/document-segments.json \
  --evidence /protected/path/evidence-matrix.json \
  --claim-id CLM-001 \
  --evidence-id EVD-001 \
  --output /protected/path/revisao/pacote-fontes-clm-001.md
```

Repita `--evidence-id` apenas para outras evidências do **mesmo** pedido. O
diretório de saída deve existir, ser privado e estar fora do Git; não há
sobrescrita. O pacote conserva texto extraído por página, não uma imagem fiel
da página: confira o PDF original antes de qualquer conclusão jurídica. Falha
de extração de texto exige tratamento separado, não preenchimento inferido.

Se houver vários pedidos encaminhados a `evidence_analysis`, prepare os pacotes
de uma vez no diretório privado do caso (`0700`), fora do repositório. O PDF,
`issue-route.json` e `evidence-matrix.json` devem estar diretamente nesse
diretório:

```bash
python3 scripts/prepare_documentary_claim_packets.py \
  --workspace /protected/path/caso \
  --pdf /protected/path/caso/processo.pdf
```

O comando deriva os IDs de evidência de cada pedido, confere o PDF original e
publica um pacote `CLM-xxx-source-evidence-packet.md` por pedido, além de
`documentary-pje-pdf-segments.json` e `documentary-packet-index.json`, todos
com `0600` e sem sobrescrita. Se algum pedido não tiver evidência válida, não
publica saídas parciais. O índice registra os hashes para conferência local;
esses arquivos são dados sensíveis e não devem ser incluídos no Git. Isso não
executa o agente documental, não envia dados a provedor e não substitui a
revisão jurídica.

Uma observação gerada a partir desse pacote segue o contrato
`runtime/pipelines/documentary-observations.v1.schema.json` e pode ter suas
âncoras conferidas localmente, sem enviar o PDF a provedor:

```bash
python3 scripts/validate_documentary_observations.py \
  --result /protected/path/revisao/observacoes-clm-001.json \
  --packet /protected/path/revisao/pacote-fontes-clm-001.md \
  --pdf /protected/path/processo.pdf \
  --segments /protected/path/document-segments.json \
  --evidence /protected/path/evidence-matrix.json \
  --claim-id CLM-001 \
  --evidence-id EVD-001
```

O validador exige os mesmos IDs selecionados na preparação e não imprime
trechos dos autos. O retorno `[OK]` confirma cobertura, pacote e citações
literais, **não** a interpretação, autenticidade ou força da prova. Mantenha a
saída protegida fora do Git e submeta conclusões a revisor jurídico antes de
qualquer uso decisório. A variante documental ainda não é executada
automaticamente pelo pipeline.

Para repetir somente o ensaio fictício no Codex, prepare um diretório externo
ao Git, privado (`0700`) e vazio, e execute:

```bash
python3 scripts/run_codex_documentary_rehearsal.py \
  --workspace /protected/path/ensaio-documental-vazio \
  --model gpt-6-sol \
  --synthetic-rehearsal
```

O comando gera seu próprio PDF fictício e recusa arquivos preexistentes.
Publica PDF, segmentos, matriz, pacote, observações, dois fragmentos da trilha
probatória e um resumo de hashes apenas após a validação; os arquivos são
criados com `0600`, sem sobrescrita. `--model` é obrigatório, e o resumo
registra o identificador solicitado ao CLI. A saída permanece
`pending_human_review` ou `insufficient`, com `assessment` vazio. Os
fragmentos não devem substituir isoladamente os artefatos completos do
checkpoint condicional. Esse comando não aceita um PDF real nem habilita o
agente documental no fluxo de processos.

Para um espaço de trabalho protegido que já contenha contexto, índice PJe,
matriz de pedidos, rotas, matriz de provas, corpus de precedentes e revisão de
cálculos, `scripts/compose_documentary_conditional_stage.py` oferece uma
função local de composição. O chamador fornece um pacote documental validável
para **cada** pedido encaminhado a `evidence_analysis` e os recibos completos
das demais trilhas. A função reconfere o PDF e as citações, produz
`evidence-review.json`, `conditional-work-results.json` e o registro auxiliar
`documentary-source-register.json` com `0600`, sem sobrescrever arquivos, e
submete os artefatos ao checkpoint já existente. O PDF deve estar diretamente
no diretório privado do caso. Na retomada, o controle reconfere o PDF, os
segmentos, o pacote e as observações vinculados pelos hashes publicados; fonte
alterada ou registro ausente invalida o checkpoint. Uma recusa remove somente
as três saídas recém-criadas. Pedidos sem trilha
probatória recebem `not_required`; os encaminhados permanecem
`pending_human_review` ou `insufficient`, nunca `reviewed` por automação.
Não há interface de linha de comando nem despacho automático desse compositor;
o ensaio disponível é sintético. A revisão jurídica e a autorização para autos
reais continuam indispensáveis antes de qualquer uso decisório.

Quando existirem pacotes em lote, salve uma saída protegida
`CLM-xxx-documentary-observations.json` para **cada** pedido do índice. A função
`load_documentary_claim_bundles(workspace)` lê os arquivos, exige cobertura
exata das rotas probatórias e reconfere PDF, segmentos, hashes, IDs e trechos
literais antes de devolvê-los ao compositor. A função
`accept_documentary_conditional_stage_from_files(...)` usa esse carregamento e
o executor de checkpoint acima, mantendo os mesmos insumos de plano, estado,
escopo de autorização e recibos das outras trilhas. Ausência ou alteração de
uma observação recusa o lote inteiro sem publicar a etapa. Essas funções são
interfaces Python locais, não comandos de despacho de modelo; nenhum arquivo
de observação pode ser tratado como conclusão jurídica automática.

O vínculo `scripts/run_documentary_conditional_stage.py` recebe também o plano
e o estado de execução compartilhados. Antes de compor, revalida os checkpoints
anteriores e exige que a próxima etapa seja `execute-conditional-tracks`.
Depois, registra essa etapa pelo mecanismo de retomada existente; se o registro
falhar, remove somente as três saídas que acabou de criar. O novo estado é
devolvido ao chamador. Com `state_output`, a mesma chamada também o grava uma
única vez em arquivo `0600` no diretório privado do caso, sem substituir estado
existente; sem esse argumento, não o salva. No ensaio sintético, a
retomada passa então a indicar `analyze-claims`. Esse vínculo é uma função
local, não um comando de despacho nem permissão para enviar autos ao modelo.

Para ligar o ensaio fictício do Codex a esse checkpoint, use a função local
`run_codex_documentary_stage` com `synthetic_rehearsal=True`, modelo explícito,
plano/estado já aceitos até `route-claims`, diretório de ensaio vazio e privado
e matriz probatória igual à amostra fixa. Antes da chamada ao modelo, ela
confere que `execute-conditional-tracks` é a próxima etapa. O importador
verifica hashes, instruções do agente, fragmentos e a identidade do PDF
fictício; só então copia a fonte para o espaço do caso e registra o checkpoint.
Falha de importação não substitui arquivos preexistentes. Um ensaio local com
Codex CLI chegou a `pending_human_review` e ao checkpoint aceito; não houve
envio de autos reais nem avaliação jurídica. A função não é um comando de
processamento de processos reais.

## 8. Validar a verificação prévia específica do processo

Crie o JSON protegido de verificação prévia fora do repositório, conforme
`runtime/operations/pilot-preflight.v4.schema.json`. As versões 1 a 3
permanecem como contratos históricos. A versão atual exige o número CNJ
somente no registro local protegido e `valid_until` posterior à criação; não
aceita registro futuro ou vencido. Também exige lista explícita de provedores
autorizados em `model_providers_authorized`; o piloto Codex requer `codex`
nessa lista e um `codex_model_id` explícito para fixar o modelo usado em cada
despacho. A verificação confere a contagem de
artefatos e o resumo do contrato com o manifesto vigente. Use resumos
criptográficos no registro sem segredos, nunca o número do processo ou texto
da autorização. O
contrato registra responsáveis, commit exato de `development`, evidências de
host e qualidade, resumos idênticos de Claude/Codex, mapa de endpoints
revisado, classificação do processo, prazos, operações locais permitidas e
proibição permanente de atos judiciais externos. A retenção do HAR bruto
conta da captura, não da verificação prévia posterior.

Crie diretórios existentes e separados fora do checkout para fonte autorizada
e novas saídas. O diretório de saída deve estar vazio. Depois execute:

```bash
python3 scripts/validate_pilot_preflight.py \
  --preflight /protected/path/pilot-preflight.json \
  --endpoint-map /protected/path/reviewed-endpoint-map.json \
  --workspace /protected/path/authorized-case-workspace \
  --output /protected/path/new-pilot-output \
  --summary /protected/path/pilot-preflight-summary.json
```

`[GO]` autoriza somente as operações locais e de leitura indicadas. O
validador retorna `NO-GO` para processo sigiloso ou com acesso excepcional,
espaço dentro do repositório, commit vencido, árvore suja, evidência de host ou
qualidade reprovada, resumos divergentes, mapa incompleto ou alterado,
retenção excessiva, verificação prévia futura ou vencida, saída não vazia ou
divergência de contrato. O resumo sem
segredos não contém número do processo, alcance da autorização, caminho local,
credencial nem texto dos autos. Grupos de falha não observados naturalmente
permanecem em `unobserved_failure_groups`, sem serem tratados como observados
ou exigirem que o operador provoque a falha.

Após o `GO` e com os três insumos já revisados no espaço de origem, a
preparação protegida pode ser executada com os caminhos reais do relatório,
da matriz e da entrada correspondente:

```bash
python3 scripts/prepare_codex_pilot_handoff.py \
  --preflight /protected/path/pilot-preflight.json \
  --endpoint-map /protected/path/reviewed-endpoint-map.json \
  --workspace /protected/path/authorized-case-workspace \
  --output /protected/path/new-pilot-output \
  --report /protected/path/authorized-case-workspace/labor-report.json \
  --matrix /protected/path/authorized-case-workspace/claim-matrix.json \
  --input /protected/path/authorized-case-workspace/triage-input.md
```

O registro de verificação prévia e ambos os diretórios devem ser privados.
A rotina não consulta PJe, não chama o modelo e não autoriza o uso judicial;
os comandos diretos do Codex continuam limitados ao ensaio sintético.

O despachante `scripts/run_codex_pilot.py` **recusa no código qualquer relatório
e matriz diferentes da amostra sintética versionada antes de preparar a saída**.
Os despachos internos do relator e do triador repetem essa verificação antes
da chamada ao modelo. Portanto, não tente executá-lo com autos reais neste
host. A configuração do CLI desabilita shell, pesquisa, aplicativos conectados
e subagentes; mesmo assim, um ensaio
sintético em 2026-09-24 registrou chamadas às ferramentas de listagem de
recursos MCP internas do Codex. Portanto, a configuração ainda não demonstra
ausência total de ferramentas ou isolamento de leitura de outros arquivos
locais. Antes do primeiro despacho real, escolha e valide uma execução sem
ferramentas por API ou um ambiente dedicado com acesso delimitado aos dados.
Uma resposta textual `SEM_FERRAMENTA` do agente, isoladamente, não é prova
desse limite técnico.

Há um segundo caminho de ensaio que usa a Responses API, mas ele aceita
**somente a amostra sintética versionada**. Depois de preparar um diretório
externo, vazio e privado, prepare os insumos. Um operador com chave de API
configurada no ambiente pode então executar:

```bash
python3 scripts/prepare_codex_agent_rehearsal.py \
  --workspace /protected/path/synthetic-workspace
python3 scripts/run_openai_synthetic_rehearsal.py \
  --workspace /protected/path/synthetic-workspace \
  --model MODEL_ID \
  --synthetic-rehearsal
```

Não inclua a chave de API na linha de comando, em arquivos do repositório ou
em logs. A requisição declara `tools: []`, `tool_choice: none` e `store: false`;
o cliente também exige que a resposta confirme esses campos e não indique
conversa nem resposta anterior. A geração tem limite de 8192 tokens de saída,
incluídos os tokens de raciocínio; respostas incompletas não são publicadas.
Isso não equivale a certificação de retenção zero nem autoriza o envio de autos.
Até agora o caminho foi exercitado apenas com respostas HTTP simuladas. Antes
de chamar a API com a amostra sintética, confirme disponibilidade do modelo,
credencial, condições do provedor e aprovação operacional do ensaio.
O campo `codex` da verificação prévia v4 refere-se ao fluxo Codex do piloto;
ele **não** autoriza, por equivalência, a transmissão de autos pela API da
OpenAI. Essa autorização precisará de contrato e registro específicos antes
de se cogitar um despacho real pela Responses API.

O contrato suplementar
`runtime/operations/openai-api-authorization.v1.schema.json` registra essa
autorização específica sem alterar o contrato v4 do Codex CLI. O responsável
pelos dados deve vincular o registro protegido ao mesmo piloto, processo,
escopo, classificação de acesso e prazo; identificar o modelo da Responses
API; e registrar o resumo do documento do provedor que examinou. O comando
abaixo apenas confere essa vinculação, sem ler autos nem chamar a API:

```bash
python3 scripts/validate_openai_api_authorization.py \
  --preflight /protected/path/pilot-preflight.json \
  --authorization /protected/path/openai-api-authorization.json
```

Os dois registros devem estar fora do repositório, sem vínculo simbólico e
com permissão `0600`. Um registro preenchido não comprova por si só a
identidade de quem o declarou, a adequação das condições do provedor ou a
autorização para um processo concreto; o comando **não concede GO ao piloto**.
O despacho real pela API permanece desabilitado. Nunca use a autorização
`codex` do contrato v4 como substituta deste registro específico.
O código de integração `run_openai_pilot.py` já reutiliza o relator, o triador
e os três controles de transferência do piloto, mas possui um bloqueio fixo
de despacho real nesta versão. Os testes exercitam o caminho interno com
HTTP substituído e dados fictícios; não houve ensaio sintético na API real.
`verify_openai_pilot_result.py` reconfere, sem chamar o modelo, o resumo,
os arquivos protegidos, a autorização específica e os três controles de
transferência dos resultados simulados. Uma verificação técnica positiva
mantém o estado `pending_legal_review`.
Não execute `run_openai_pilot.py` com autos até existir evidência do ensaio real,
revisão de privacidade e uma alteração revisada que remova o bloqueio.

Antes de qualquer despacho real, será necessário implementar e validar um
transporte sem ferramentas ou um ambiente dedicado, remover de forma
controlada a restrição sintética nesses três pontos e repetir os testes de
segurança. Só então, com o GO específico do processo vigente, use o
despachante validado **em vez** do preparador, com os mesmos argumentos e
outro diretório de saída novo e vazio. Não execute os dois comandos em
sequência sobre a mesma saída: ambos recusam sobrescrita. O orquestrador
confere o GO novamente antes de cada chamada ao modelo, interrompe o fluxo
se o prazo, o checkout ou algum insumo mudar e deixa qualquer saída parcial
protegida para revisão de incidente. Este caminho ainda não foi exercitado
com processo real. A chamada transmite ao Codex os dados estruturados do
processo autorizado; confirme o alcance dessa autorização e a presença do
revisor jurídico antes de usá-la.
O resultado técnico é registrado em `pilot-run-summary.json`, com hashes e
estado `pending_legal_review`. Esse estado exige conferência humana dos
artefatos e não equivale a aprovação de minuta ou autorização de ato externo.

Após a execução, confira o conjunto protegido de forma independente:

```bash
python3 scripts/verify_codex_pilot_result.py \
  --workspace /protected/path/new-pilot-output \
  --preflight /protected/path/pilot-preflight.json
```

O verificador é somente leitura: confere hashes, vínculo com a autorização
histórica e os três controles de transferência. Pode ser executado depois do
vencimento do GO, mas **não** renova autorização nem substitui a revisão
jurídica. Se retornar `NO-GO`, preserve os arquivos para diagnóstico e não
aprove a triagem ou qualquer minuta derivada.

Se o fluxo supervisionado chegou à minuta consolidada no mesmo espaço privado
do processo, prepare um roteiro para o revisor jurídico sem alterar o estado
do pipeline:

```bash
python3 scripts/prepare_final_human_review.py \
  --workspace /protected/path/caso
```

O comando reaplica o controle técnico de fusão, registra os resumos SHA-256
dos insumos e cria `final-human-review.md` e `final-human-review.json` em modo
`0600`, sem sobrescrever arquivos existentes. O JSON começa com todos os
pedidos em `pending`. O revisor deve ter congelado antes o inventário cego
dos pedidos e confrontar cada item com o PDF original, as provas, fontes e
cálculos. Depois de preencher sua identidade declarada, data, conferências,
decisão e justificativa por pedido no JSON, execute:

```bash
python3 scripts/validate_final_human_review.py \
  --workspace /protected/path/caso
```

O validador confere a cobertura, os vínculos e os hashes atuais. Se houver
correção, impossibilidade de avaliar ou resultado proposto ainda em
`pending_human_review` ou `abstained`, retorna `requires_followup`. Somente
declarações completas e concordantes sobre resultados propostos já resolvidos
retornam `reviewed_for_consideration`. Nenhum estado autentica o revisor, certifica a
qualidade jurídica, altera o checkpoint `review-and-gate`, converte
`pending_human_review` em decisão, ou autoriza assinatura, publicação ou outro
ato externo. Um `global-gate.json` sintético aprovado também não dispensa a
revisão. Guarde os dois arquivos fora do Git e refaça a conferência se algum
insumo mudar.

## 9. Registrar o ensaio

Para cada execução controlada, mantenha registro local sem segredos com:

```text
Commit:
Operador:
Início:
Conclusão:
Resumo de prontidão do host:
Resultado do controle de qualidade:
Resumo sintético Claude:
Resumo sintético Codex:
Resultado da revisão da captura autorizada:
Escopo do processo real, se aplicável:
Situação do controle final:
Lacunas ou incidentes observados:
```

Não registre cookies, tokens, valores de cabeçalhos, texto bruto dos autos,
nomes das partes ou conteúdo de documentos protegidos nesse resumo.

## 10. Regras de parada e recuperação

- Não ignore um controle global reprovado ou bloqueado.
- Não amplie limite de tentativas persistido para forçar êxito.
- Retome apenas de checkpoint cuja requisição, catálogo e resumos do conteúdo
  aceito ainda correspondam.
- Preserve espaço de trabalho reprovado até registrar diagnóstico sem segredos.
- A minuta é consultiva e exige revisão jurídica humana; nunca é instrução
  para assinar ou publicar.
- Se a fonte oficial limitar consultas, aguarde a janela publicada em vez de
  repetir tentativas continuamente.
