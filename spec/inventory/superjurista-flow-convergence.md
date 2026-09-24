# Convergência do fluxo SuperJurista — primeiro grau do TRT12

Esta é uma adaptação do projeto existente. O fluxo de agentes herdado do
SuperJurista é a base; os contratos e as verificações determinísticas do TRT12
o sustentam, sem criar um segundo fluxo concorrente de análise jurídica.

| Etapa herdada | Situação no TRT12 | Condição para a próxima integração |
|---|---|---|
| Conversão do PDF e linha do tempo | O conversor e o agente de linha do tempo existentes continuam disponíveis; a extração estruturada do TRT12 usa atualmente outro caminho determinístico | Comparar os dois caminhos no mesmo processo autorizado e manter um único produtor aceito por artefato |
| `relator-marmelstein` | Variante TRT12 vinculada à etapa `narrate-record`; uma execução do Codex sobre dados sintéticos produziu narrativa aceita pelo verificador de cobertura | Confrontar o texto com as fontes de um caso autorizado e manter `labor-report.json` como referência única |
| `triador-processual` | A variante TRT12 preserva a rota C2 herdada sem pesquisa da Justiça Federal; uma execução do Codex sobre dados sintéticos produziu triagem e rota por pedido aceitas pelo importador e pelo checkpoint | Revisar juridicamente as rotas num caso autorizado; ainda não há execução equivalente comprovada no Claude Code |
| Agentes condicionais de pesquisa e prova | O padrão de orquestração é reutilizável, mas as fontes federais não são autoridades do TRT12 | Vincular fontes aprovadas do TST/TRT12 e caracterizar os caminhos de análise probatória trabalhista |
| Análise de mérito e redação | As variantes do analisador e do fundamentador herdados consumiram, em sequência, a revisão documental fictícia atual; o Codex CLI chegou aos checkpoints `analyze-claims` e `draft-judgment`. O fundamentador produz apenas a matriz do dispositivo; a minuta vem do renderizador existente. O redator herdado, que consolida revisões, ainda não está vinculado. Aferição jurídica real não ocorreu | Submeter análise/minuta a revisão jurídica humana e avaliar o redator somente após o relatório de revisão; manter a fusão e o controle final sem publicação decisória enquanto houver pedido pendente |

A [auditoria dos seis agentes probatórios herdados](auditoria-agentes-probatorios-herdados.md)
separa o núcleo reaproveitável de seus pressupostos de outros ramos. Ela
prioriza uma variante documental vinculada a pedidos e fontes, posterga as
variantes testemunhal, pericial e digital até revisão, e exclui do primeiro
produto mínimo o agente de reconhecimento penal. Nenhum desses agentes foi
habilitado no manifesto TRT12 apenas por causa da auditoria.

O `inventariador-probatica` herdado precisa atuar **antes** da matriz de provas:
sem ela, a preparação por `evidence_id` é circular. O preparador
`scripts/prepare_evidence_inventory_packets.py` agora entrega um pacote por
documento do PDF, com texto por página e pedidos apresentados como alegações,
sem valorar provas. A variante
`scaffold/agents/analise/inventariador-probatica-trt12.md` e o contrato
`evidence-inventory-observations.v1.schema.json` especificam itens descritivos
por documento. O validador recompõe o pacote do PDF e confere trechos literais,
páginas e IDs, mas não prova exaustividade nem valida a associação semântica a
pedidos. `scripts/validate_evidence_inventory_batch.py` exige observações para
todos os documentos do índice e recusa arquivos faltantes ou extras; seu
resultado é cobertura técnica, não achado probatório. Nenhum despacho do agente
com autos reais nem conversão automática em `evidence-matrix.json` foi
autorizado; essa ligação e a revisão humana são os próximos controles
necessários. `scripts/run_codex_inventory_rehearsal.py` executou a variante
somente sobre PDF fictício com dois documentos, reaproveitando o despachante
Codex sem ferramentas; publicou observações protegidas após validação do lote.
O PDF TRT12 autorizado foi apenas inspecionado em memória para confirmar o
formato do sumário e a extração de texto.

`scripts/review_evidence_inventory.py` prepara um registro privado com decisão
pendente para cada item e confirmação pendente para cada documento. A validação
posterior confere a cobertura e preserva adiamentos ou omissões como lacunas;
ela não autentica o revisor e não promove observações automaticamente para a
matriz de provas.

O roteiro opcional de `prepare_evidence_inventory_review_packet.py` organiza
páginas e observações para o revisor consultar o PDF original. Ele não edita o
registro de revisão nem substitui a avaliação jurídica.

Com revisão declarada sem pendências, `build_reviewed_evidence_candidates.py`
chama o `build_evidence_matrix.py` herdado, preserva um mapa `INV` → `EVD`
com hash da revisão e publica `evidence-matrix-candidates.json` e
`evidence-selection-provenance.json`, sem criar a matriz canônica.
`evidence-matrix.json` segue como contrato canônico separado; esta ponte não
atribui resultado probatório nem libera a etapa jurídica por si só.

`verify_reviewed_evidence_candidates.py` reconstrói e compara, sem escrita,
os candidatos e a proveniência publicados com as fontes atuais. Uma
divergência bloqueia o uso do conjunto; uma conferência técnica positiva não
promove a matriz canônica nem comprova revisão jurídica.

Depois de aprovação humana declarada e vinculada aos hashes atuais, o comando
`promote_reviewed_evidence_matrix.py` pode copiar exatamente os candidatos
para `evidence-matrix.json` e publicar um recibo privado. Sua conferência
independente volta a validar fontes, aprovação, matriz e recibo. Isso fecha a
ligação técnica com o produtor canônico do fluxo herdado, mas o sistema não
autentica a qualificação do revisor nem conclui que a seleção está juridicamente
correta; sem aprovação, a promoção permanece bloqueada.
O controle `build-decision-units` repete essa conferência quando encontra
qualquer arquivo do caminho de inventário revisado. Assim, um recibo ausente
ou alterado não passa como matriz aceita; o ensaio sintético tradicional, sem
esse caminho, continua com suas verificações próprias.
Um teste de integração com PDF e revisão fictícios confirmou os dois estados:
checkpoint aceito com aprovação e recibo íntegros, e recusado quando o recibo
é retirado. Essa evidência é técnica e não substitui a revisão jurídica do caso.

`scaffold/agents/analise/analisador-marmelstein-trt12.md` adapta o método
herdado de examinar versões e objeções por questão ao contrato estruturado
`claim-analysis.json`. O manifesto compartilhado vincula a variante a
`analyze-claims` e inclui o resumo das instruções no contrato resolvido para
Claude Code e Codex. A instrução exige uma análise para cada pedido, fontes
conferidas e revisão pendente ou abstenção diante de lacunas; não aproveita a
exceção herdada que obrigava a concluir após uma escalada. O vínculo no grafo
não é autorização de uso em processo real.

`scripts/run_codex_claim_analysis_rehearsal.py` despacha exclusivamente a
amostra fictícia versionada, sem ferramentas configuráveis, e exige
`pending_human_review`, `facts_found` vazio, nenhuma regra ou fonte de
precedente tratada como conferida e apenas `EVD-001`. O resultado passa pelo
checkpoint `claim-analysis-coverage` antes de ser publicado com permissão
`0600` fora do repositório. Um primeiro despacho de 2026-09-24 foi recusado:
o modelo incluiu `TST-001` em `precedent_source_ids`, embora reconhecesse que
a referência era sintética. A instrução passou a distinguir custódia de
precedente conferido. Na repetição com `gpt-6-sol` solicitado, o Codex CLI
produziu a análise com revisão pendente e o checkpoint a aceitou. O ensaio
prova compatibilidade técnica dessa amostra, não qualidade jurídica, identidade
interna do modelo, integração automática ao executor retomável ou aptidão
para autos reais.

`scripts/run_claim_analysis_stage.py` já publica uma análise estruturada
fornecida pelo chamador **somente** quando a retomada comprova que
`analyze-claims` é a próxima etapa. A saída é criada uma vez, com acesso
`0600`, e o checkpoint é registrado pelo controle `claim-analysis-coverage`.
Um ensaio com as etapas anteriores aceitas e revisão documental fictícia
avançou para `draft-judgment`. Uma conclusão de mérito sem revisão probatória
foi recusada, sem deixar o arquivo de análise publicado. O estado novo também
pode ser gravado uma vez no espaço privado; essa função não chama modelo nem
confere, por si, a origem de um JSON fornecido. A conferência do resumo e
dos insumos precisa ocorrer na camada de importação antes do uso dessa função.

`scripts/import_codex_claim_analysis_rehearsal.py` fechou a importação
**somente da amostra fictícia fixa**: exige dois arquivos privados, resumo
compatível com o modo de execução declarado, hash da análise, hash do agente
e do fixture, identidade do modelo solicitada, plano Codex e os sete insumos
idênticos aos enviados ao modelo e índice/cargas PJe sintéticos. Somente depois usa
`run_claim_analysis_stage.py`. Testes recusam resposta modificada e insumo
atual divergente sem publicar saída. Uma resposta gerada anteriormente pelo
Codex CLI com `gpt-6-sol` foi importada para um espaço sintético temporário;
a retomada reconheceu nove checkpoints e apontou `draft-judgment` como próximo.
O resumo é evidência de integridade declarada, não assinatura ou autenticação
do serviço. Ele permanece no espaço privado do ensaio e precisa ser retido
para auditoria. O importador continua limitado ao conjunto fixo: recusa
corretamente os artefatos variáveis da ponte documental.

`scripts/run_codex_claim_analysis_stage.py` executa o mesmo analisador com
os **sete insumos atuais** depois de `execute-conditional-tracks`. Antes do
despacho, exige origem fictícia: identidade da amostra versionada, índice e
cargas sintéticos, PDF exato, registro da observação documental e revisão
derivada da citação validada nesse PDF. Recusa saída ou estado já ocupado,
tentativa inválida, alteração dos insumos durante o despacho e conclusão que
afirme fatos, regras ou precedentes ainda não conferidos. Registra em recibo
privado os resumos das fontes, instruções, entrada, comando enviado e análise;
somente então entrega a análise ao controle de cobertura. Em 24/09/2026, o
Codex CLI solicitado com `gpt-6-sol` percorreu a etapa documental e esta
análise no mesmo espaço sintético: nove checkpoints aceitos, próximo
`draft-judgment`, resultado `pending_human_review` e SHA-256 da análise
`518a4ee11e355110ad47725983e07b1779296223ff1bc76733cc5f6a56f8f24c`.
O recibo prova o vínculo local entre bytes e execução declarada, não autentica
o serviço ou a qualidade jurídica. O PDF real não foi enviado.

`scaffold/agents/analise/fundamentador-marmelstein-trt12.md` preserva a
clareza, a simetria dos argumentos e o vínculo fundamento–conclusão do agente
herdado. Retira o modelo previdenciário, comandos federais de honorários e
assinatura; sua única saída é `disposition-matrix.json`, com um item por
análise. Resultado pendente ou abstido recebe exclusivamente o texto de
ausência de comando exigido pelo controle. O manifesto compartilha esse
vínculo entre Claude Code e Codex. `run_draft_judgment_stage.py` só publica
a matriz e a minuta determinística quando `draft-judgment` é a próxima etapa;
o controle de congruência precisa aceitar ambas, senão os arquivos novos são
retirados. Os testes fictícios avançam ao checkpoint de fusão e recusam uma
condenação inserida num pedido ainda pendente. O redator herdado é uma
função posterior à revisão, não um substituto do fundamentador nesta etapa.

`scripts/run_codex_draft_stage.py` usa o fundamentador com os mesmos sete
insumos documentais fictícios atuais e com a análise já aceita no checkpoint.
Antes do despacho, confere o recibo privado da análise, os resumos dos
insumos, o resumo reconstruído do comando do analisador, a origem do PDF
sintético e a ordem da retomada; recusa destino de
estado conflitante e saída já existente. O dispositivo pendente é conferido
antes da renderização determinística da minuta, da publicação protegida e do
checkpoint `draft-congruence`. O recibo novo vincula análise, recibo anterior,
instruções, entrada, dispositivo e minuta. Em 24/09/2026, uma execução efetiva
do Codex CLI solicitado com `gpt-6-sol` percorreu as etapas documental,
análise e fundamentação no mesmo ensaio fictício: dez checkpoints aceitos,
próximo `merge-judgment`, dispositivo SHA-256
`136ddb502355b66c7dc64ad1023b2395d8e7b4985464feaca4263145f6afaf6d`
e minuta SHA-256
`ce857eaf6ceeff23bd5ec434d7d79410aed05512b98ae418237f8d8f5e3f31ec`.
O resultado continua `pending_human_review`; os recibos locais não autenticam
o serviço nem certificam interpretação jurídica. Nenhum auto real foi enviado.

`scripts/run_codex_draft_rehearsal.py` executa essa variante somente com a
amostra fictícia versionada e uma análise anterior cujo arquivo e resumo são
conferidos. O resultado do Codex CLI, solicitado com `gpt-6-sol` em
2026-09-24, manteve `pending_human_review` e o texto exato de ausência de
comando. A matriz (`136ddb502355b66c7dc64ad1023b2395d8e7b4985464feaca4263145f6afaf6d`)
e a minuta (`b2af03e398da775db1c3f889e4bcceaaaa6afc7bba964758e7b832fe05838a47`)
passaram por `draft-congruence` e foram guardadas com acesso `0600` fora do
repositório. Esses hashes identificam os bytes aceitos, não autenticam o
serviço nem certificam o conteúdo jurídico.

`scripts/import_codex_draft_rehearsal.py` vincula resumo, instruções, análise
anterior, minuta renderizada e os insumos sintéticos atuais antes de registrar
`draft-judgment`. A saída efetiva do Codex CLI foi importada em espaço
temporário de teste, depois da análise efetiva, e a retomada reconheceu dez
checkpoints com `merge-judgment` como próximo. Uma alteração posterior da
minuta é recusada antes da publicação. Esse importador permanece restrito à
amostra fixa; o despacho documental atual utiliza o executor descrito acima.
Não houve revisão jurídica de autos reais.

`scripts/run_merge_judgment_stage.py` fecha a próxima ligação determinística:
somente depois do checkpoint da minuta, copia seus bytes sem alteração para
o arquivo nomeado pelo número do processo, cria o arquivo com acesso `0600`
e registra `merge-judgment`. Um ensaio retomado com as respostas efetivas do
Codex CLI alcançou onze checkpoints e apontou `review-and-gate` como próxima
etapa. O controle final recusou o pedido ainda em `pending_human_review`, como
deve ocorrer; o arquivo fundido permanece artefato de revisão, não sentença
apta para assinatura ou publicação. Isso não supre a revisão jurídica nem a
entrada variável de um processo real.

A repetição com as etapas documental, análise e fundamentação
encadeadas sobre os insumos fictícios **atuais** também alcançou onze
checkpoints. A minuta e o arquivo fundido tiveram o mesmo SHA-256,
`cbbcafb35640498251f03998a68ff853046ae1f71bd2bacb44565ed7477dd80d`;
`review-and-gate` permaneceu bloqueado. Essa repetição não incluiu autos reais
nem revisor jurídico.

```bash
espaco_ensaio=$(mktemp -d -t trt12-claim-analysis-XXXXXX)
chmod 700 "$espaco_ensaio"
python3 scripts/run_codex_claim_analysis_rehearsal.py \
  --workspace "$espaco_ensaio" --model gpt-6-sol --synthetic-rehearsal
```

A primeira variante, `scaffold/agents/analise/analista-documental-trt12.md`,
já foi ensaiada no Codex com PDF fictício produzido localmente. O comando
`scripts/run_codex_documentary_rehearsal.py` não aceita caminho de autos:
gera o PDF e a matriz sintéticos, prepara o pacote por `evidence_id`, envia
somente esse conteúdo ao agente com as superfícies configuráveis de ferramentas
desabilitadas e valida a cobertura e as citações literais antes de publicar
arquivos em diretório privado externo. Em 2026-09-24,
`codex-cli 0.155.0-alpha.16.3` devolveu `pending_human_review` com trecho
literal da página 2; o validador local aceitou a saída. O ensaio inicial usou
o modelo padrão sem registrá-lo. Depois, uma repetição solicitou explicitamente
`gpt-6-sol` e gravou resumos SHA-256 do PDF fictício, pacote, instruções do
agente, observações e dois fragmentos da trilha probatória. O resumo registra
o modelo solicitado, não prova o identificador interno de um snapshot do
serviço. `scripts/build_documentary_work_records.py` deriva um registro
`evidence-review` ainda pendente ou insuficiente e um recibo
`conditional-work-results` a partir das observações validadas, exigindo
cobertura integral das evidências do pedido. O compositor
`scripts/compose_documentary_conditional_stage.py` combina esses registros
com os recibos das outras trilhas, exige todos os pedidos encaminhados à prova
e publica os dois artefatos completos apenas se o checkpoint herdado
`execute-conditional-tracks` os aceitar junto ao corpus e à revisão de
cálculos. Também publica `documentary-source-register.json`, registro auxiliar
privado que vincula as observações ao PDF no mesmo espaço do caso. A retomada
reconfere o PDF, o pacote e os hashes das observações; alterar ou retirar a
fonte invalida o checkpoint. Um ensaio sintético cobre aceite, abstenção, citação falsa, recibo
probatório externo, colisão e reversão de publicação. Isso ainda não liga o
despacho do agente automaticamente ao manifesto nem comprova conferência
jurídica ou teste com autos reais.
`scripts/run_documentary_conditional_stage.py` já exige que a retomada do
manifesto compartilhado aponte para `execute-conditional-tracks`, compõe as
saídas e devolve o estado com o checkpoint aceito pelos controles TRT12. Um
teste com todos os sete checkpoints anteriores em dados fictícios avança para
`analyze-claims`; sem `route-claims` aceito, não publica saídas. Esse vínculo
não despacha o agente nem autoriza processamento de autos reais. Quando o
chamador informa `state_output`, grava o novo estado uma única vez, com acesso
`0600`, no diretório privado do caso; colisão ou falha de registro não deixa
as três saídas novas da etapa publicadas.
`scripts/import_codex_documentary_rehearsal.py` confere a identidade fixa da
amostra fictícia, os hashes do resumo, a versão das instruções do agente, o
PDF, a matriz e os fragmentos antes de copiar a fonte com `0600` para o
espaço do pipeline e registrar o checkpoint. O vínculo
`scripts/run_codex_documentary_stage.py` só chama o agente depois de a
retomada confirmar essa etapa. Um ensaio local com resposta simulada e outro
com despacho efetivo pelo Codex CLI chegaram a `execute-conditional-tracks`
com `pending_human_review`. Isso integra o despacho **sintético**; não oferece
um caminho autorizado para enviar autos reais nem valida a interpretação
jurídica das observações.

A primeira ponte implementada é `scripts/build_superjurista_triage_input.py`.
Ela lê o relatório estruturado e a matriz de pedidos já produzidos, verifica a
cobertura de pedidos e defesas e a coerência das fontes e dos resumos, e cria
uma entrada Markdown protegida para o triador herdado. Não relê a petição,
decide a rota, executa um agente, valida o acerto jurídico nem autoriza um ato
judicial.

`scaffold/agents/extracao/relator-marmelstein-trt12.md` preserva o papel
cronológico e narrativo do relator herdado, mas retira os pressupostos
previdenciários. Sua entrada prevista é o relatório e a matriz de pedidos
protegidos; sua saída é texto para conferência humana, nunca uma substituição
de `labor-report.json`. O validador `scripts/validate_superjurista_report.py`
confere a entrada protegida atual, o número do processo, seu SHA-256, os
marcadores herdados e a cobertura exata de IDs e localizadores de pedidos e
defesas em um bloco JSON da narrativa. Dez testes sintéticos verificam aceite
e rejeições de divergências. Ele não comprova fidelidade semântica do texto
nem substitui revisão jurídica. O manifesto compartilhado coloca
`prepare-triage-input` após a matriz de pedidos e `narrate-record` após essa
entrada, antes da triagem. A etapa composta `extract-record` continua responsável
por classificação, linha do tempo e `labor-report.json`; a narrativa não os
substitui. O ensaio sintético usa texto narrativo congelado e valida sua
custódia antes de escrever saídas. Nenhum modelo foi despachado para produzi-lo.
Em ensaio separado de 2026-09-24, com `codex-cli 0.155.0-alpha.16.3`,
`scripts/run_codex_narrator.py` despachou efetivamente o Codex com essa entrada
sintética e produziu uma narrativa aceita.
Depois, `scripts/run_codex_triager.py` despachou o Codex com a narrativa validada
e produziu triagem, fontes vazias e rota por pedido aceitas. O controle de
checkpoint aprovou `prepare-triage-input`, `narrate-record` e `route-claims`
para essas saídas. Os arquivos ficaram em diretório temporário fora do Git,
com permissão `0600`; seus resumos SHA-256 foram, respectivamente,
`89ab0d6783b9ad3f6641a6f43d80fa6fd7892bb3551de3e6d26ed717307c404a`
para a narrativa, `a38bbe12e651329fc5d6dd34107b4c1153ba6e58644ffc4596136a30a64ed666`
para a triagem e `864f1be286eaaa0b1c844ff730fb9b71af605a37c1da20f59475be0a8c336129`
para a rota. Esse resultado é funcional e sintético; não comprova fidelidade
semântica ou adequação jurídica e não autoriza a execução de um processo real.
Em um segundo ensaio da mesma data, foram construídos insumos sintéticos com
oito pedidos `CLM-001` a `CLM-008`, sete defesas e um pedido sem defesa
vinculada. O Codex gerou narrativa e triagem aceitas pelos três checkpoints.
O importador preservou os oito IDs, encaminhou sete pedidos à análise
probatória e registrou abstenção explícita para o oitavo; não deduziu pesquisa
jurídica de códigos genéricos de questão. Os SHA-256 da narrativa, triagem e
rota foram, na mesma ordem,
`9de5f43b6b780a4d3e8adac475df23be2a79b5d3f7ca198c45eb4e11239d80be`,
`080ee500e65a7af029cde3330a050c74ef39a1b2d7dc7aeff6b228a016adfe68`
e `086f625e0a7d9b694222e926d5e105c3bd65f6fdb77163a67015afd7cb538e67`.
O ensaio não reproduz a complexidade documental dos autos reais nem mede o
acerto jurídico das rotas.
Após esses ensaios, os comandos diretos de despacho foram limitados à amostra
sintética versionada: exigem `--synthetic-rehearsal` e comparam integralmente
relatório e matriz antes da chamada ao modelo. O ensaio pontual de oito pedidos
não constitui uma exceção permanente para insumos arbitrários. O despacho de
um caso real ainda precisa de um caminho próprio vinculado à verificação
prévia `GO` do piloto; os comandos diretos não o oferecem.
`scripts/prepare_codex_agent_rehearsal.py` prepara os três insumos da amostra
versionada em diretório externo, vazio e privado, com arquivos `0600`. Assim,
o ensaio direto dos dois agentes pode ser repetido sem copiar autos ou apagar
saídas anteriores.
O controle `scripts/trt12_handoff_gate.py` permite aceitar os checkpoints de
entrada, narrativa e triagem com verificação atual dos insumos; recusa outras
etapas até que o executor forneça seus controles próprios. O mecanismo
compartilhado também recusa saídas apontadas por vínculos simbólicos.

```bash
python3 scripts/validate_superjurista_report.py \
  --report /protected/report/labor-report.json \
  --matrix /protected/matrix/claim-matrix.json \
  --input /protected/triage/triage-input.md \
  --narrative /protected/report/relatorio-trabalhista.md
```

```bash
python3 scripts/build_superjurista_triage_input.py \
  --report /protected/report/labor-report.json \
  --matrix /protected/matrix/claim-matrix.json \
  --output /protected/triage/triage-input.md
```

O gerador informa o SHA-256 da entrada protegida sem imprimir o texto do
processo. O orquestrador entrega o caminho e o resumo ao agente adaptado. O
agente repete o resumo em sua saída Markdown; o importador confere esse valor
e verifica se a entrada ainda corresponde ao relatório e à matriz atuais.

O caminho alternativo `scripts/run_openai_pilot.py` reutiliza esses mesmos
agentes adaptados e controles do piloto após conferir, em separado, o GO do
processo e a autorização específica da Responses API. Por enquanto, o
despacho de autos reais está bloqueado por código; somente testes com
requisições simuladas percorreram essa integração. Assim, a API não vira um
segundo fluxo de interpretação jurídica nem herda implicitamente a
autorização do Codex CLI.

O diretório de saída deve existir fora do repositório. O arquivo é criado uma
única vez, com permissão `0600`, sem sobrescrever dados existentes. Seu conteúdo
é material confidencial derivado dos autos. A ponte serve para testes sintéticos
e ensaios locais controlados. A ponte foi comprovada no Codex com entrada
sintética; a validação em um processo real ainda depende da revisão
independente, da política de fontes adequada ao TRT12 e da verificação prévia
do piloto.

`scaffold/agents/analise/triador-processual-trt12.md` adapta o papel do triador
herdado ao perfil TRT12. Ele mantém o bloco JSON C2 global e acrescenta
`rotas_por_pedido` no mesmo bloco. Não possui ferramentas de pesquisa da Justiça
Federal e escreve `fontes-triagem.json` vazio até a integração das fontes oficiais
TRT12/TST com rastreabilidade. `scripts/import_superjurista_triage.py` reutiliza
as verificações herdadas de formato e C2 e o gerador compartilhado de rotas.
Ele rejeita pedidos ausentes, divergência entre as rotas global e individuais,
fluxos incompatíveis, rotas diretas sem comprovação e fontes de triagem não vazias.
O `issue-route.json` resultante é protegido e não sobrescreve arquivos.
No ensaio sintético, o arquivo de triagem congelado e `fontes-triagem.json`
ficam entre as saídas declaradas de `route-claims`. O importador reconstrói as
rotas por pedido e qualquer diferença para `issue-route.json` bloqueia a
materialização. O checkpoint da etapa usa a mesma comparação ao aceitar a
saída. Isso exercita contratos e custódia, não a decisão jurídica de um agente.

O pipeline compartilhado do TRT12 vincula esse agente à etapa `route-claims`,
que agora depende da verificação de `narrate-record`.
Os planos dos dois ambientes de execução expõem o mesmo caminho e o mesmo
resumo das instruções. O planejador de retomada informa o agente vinculado
quando essa etapa é a próxima. Uma mudança nas instruções invalida checkpoints
anteriores por meio do resumo do contrato compartilhado. Trata-se de metadados
de despacho, não de uma execução de qualquer dos modelos.

```bash
python3 scripts/import_superjurista_triage.py \
  --report /protected/report/labor-report.json \
  --matrix /protected/matrix/claim-matrix.json \
  --input /protected/triage/triage-input.md \
  --triage /protected/triage/0000000-00.2026.5.12.0000-triagem.md \
  --sources /protected/triage/fontes-triagem.json \
  --output /protected/routes/issue-route.json
```

O ensaio automatizado com saídas congeladas é uma verificação executável de
artefatos, enquanto o ensaio separado de 2026-09-24 comprova somente a execução
dos dois agentes adaptados pelo Codex com dados sintéticos. Nenhum dos dois
comprova revisão jurídica ou execução pelo Claude Code. O agente antigo da
Justiça Federal permanece intacto para comparação;
apenas a variante TRT12 pode ser usada neste perfil.

O caminho alternativo `scripts/run_openai_synthetic_rehearsal.py` reutiliza os
mesmos prompts, validadores e saídas protegidas do relator e do triador, mas
despacha pela Responses API sem ferramentas declaradas. Antes da primeira
requisição, confere a identidade da amostra sintética, a privacidade do
diretório, colisões de saídas e a custódia da entrada. Após cada saída, aplica
os checkpoints compartilhados `narrate-record` e `route-claims`. O ensaio desse
caminho usou respostas HTTP simuladas; ainda não comprova execução real pela
API, privacidade do provedor nem adequação jurídica, e não aceita autos reais.
