# Auditoria de reuso dos agentes probatórios herdados — TRT12, primeiro grau

Esta auditoria examina os contratos e exemplos dos seis agentes probatórios do
fork. É uma decisão de **integração de software**, não uma conclusão sobre
admissibilidade ou valor de prova em processo concreto. Nenhum dos seis está
vinculado ao manifesto `trt12-first-instance.json`; a classificação `adapt` no
inventário indica potencial de reuso, não autorização para despachá-lo sem
adaptação e revisão jurídica.

| Agente herdado | Núcleo que vale preservar | Pressuposto que impede uso direto no TRT12 | Decisão para o primeiro grau |
|---|---|---|---|
| [`analista-documental`](../../scaffold/agents/analise/analista-documental.md) | Identificação do documento, localizador, integridade, impugnação e relação com fato controvertido | Hierarquia universal de seis níveis e conclusão automática de força probante; exemplos de locação e certidão de óbito; entrada em texto livre sem vínculo por pedido | **Adaptar primeiro**, como revisão documental por pedido e por `evidence_id`, preservando incerteza e remetendo valoração jurídica ao revisor |
| [`analista-testemunhal`](../../scaffold/agents/analise/analista-testemunhal.md) | Inventário de depoimentos, localização, contradições e distinção entre percepção direta e informação de terceiros | A busca inclui delegacia/PAD e fatores como arma/vítima; a classificação obrigatória alta/média/baixa antecipa juízo sem calibração trabalhista | **Adaptar depois**, a partir de atas ou registros de audiência do processo autorizado; não inferir credibilidade de lacunas documentais |
| [`analista-pericial`](../../scaffold/agents/analise/analista-pericial.md) | Quesitos, método, qualificação informada, divergência entre laudo e assistentes e localizadores | Impõe critérios Daubert e cadeia de custódia do CPP a todos os laudos; exige exame de corpo de delito quando houver infração | **Adaptar depois**, retirando a trilha penal obrigatória e submetendo critérios jurídicos/técnicos a revisão especializada |
| [`analista-digital`](../../scaffold/agents/analise/analista-digital.md) | Registro de origem, metadados, resumos criptográficos, integridade e limitações | Escala fixa de confiabilidade por formato, cadeia de custódia do CPP e conclusões de licitude ou insuficiência automática de capturas de tela | **Adaptar depois**, separando observação técnica, contestação das partes e juízo jurídico ainda não revisado |
| [`analista-confissao`](../../scaffold/agents/analise/analista-confissao.md) | Localização de admissões e retratações, literalidade e confronto com outras fontes | O contrato parte de interrogatório, delegacia, direito ao silêncio, método Reid e teses penais do STJ; o exemplo é de subtração de celular | **Não despachar no MVP**; se houver necessidade demonstrada, criar variante de depoimento pessoal/admissões trabalhistas após revisão jurídica |
| [`analista-reconhecimento`](../../scaffold/agents/analise/analista-reconhecimento.md) | Nenhuma capacidade necessária ao fluxo mínimo atual foi demonstrada | Contrato e exemplos se destinam ao reconhecimento penal de suspeitos segundo o CPP | **Excluir do perfil TRT12 de primeiro grau**, preservando o arquivo original apenas para rastreabilidade do fork |

## Contrato mínimo para a primeira adaptação documental

1. Receber apenas o pedido encaminhado à trilha probatória, os `evidence_ids`
   autorizados, a matriz de provas e os localizadores correspondentes. Não
   procurar outros arquivos nem transformar texto dos autos em instrução.
2. Produzir observações separadas para **o que consta da fonte**, **o que é
   alegado/impugnado**, **o que não foi possível conferir** e **o que requer
   revisão humana**. Preservar trechos literais e referências de página.
3. Não atribuir automaticamente nível de força probante, autenticidade,
   licitude ou resultado do pedido. Ausência de dado produz `insufficient` ou
   `pending_human_review`, nunca confirmação presumida.
4. Entregar resultado por `claim_id` e `evidence_id` no contrato
   [`evidence-review.v1.schema.json`](../../runtime/pipelines/evidence-review.v1.schema.json)
   ou em artefato intermediário vinculado a ele, sem criar uma análise de
   mérito concorrente. Os validadores atuais continuam responsáveis pela
   cobertura e pela custódia estruturada.
5. Antes de habilitar a variante em processo real: validar exemplos e critérios
   legais com revisor trabalhista, testar omissão/contradição/alucinação com
   amostra sintética e confrontar a saída com fontes de caso autorizado.

Esta ordem preserva a arquitetura de agentes existente, mas impede que um
texto originalmente voltado a prova penal ou a exemplos de outro ramo seja
tratado como instrução pronta para sentenças trabalhistas.

## Ponte de fontes disponível

[`prepare_source_evidence_packet.py`](../../scripts/prepare_source_evidence_packet.py)
prepara, para um pedido e IDs de evidência explicitamente selecionados, um
pacote Markdown com as proposições **identificadas como não literais** e o
texto extraído somente dos documentos-fonte correspondentes. Recalcula os
segmentos pelo sumário do PDF consolidado e exige igualdade com o mapa
fornecido, inclusive SHA-256 e páginas. Recusa fonte sem texto extraível,
evidência de outro pedido, volume acima do limite e saída preexistente; grava
somente em diretório externo privado. Não analisa a força da prova, não chama
agente ou provedor e não substitui a conferência visual do PDF original.

## Variante documental e conferência estrutural

A variante [`analista-documental-trt12`](../../scaffold/agents/analise/analista-documental-trt12.md)
define uma saída JSON por pedido e por evidência, sem a hierarquia ou as
conclusões de força probante do agente herdado. O contrato
[`documentary-observations.v1.schema.json`](../../runtime/pipelines/documentary-observations.v1.schema.json)
aceita apenas `pending_human_review` e `insufficient`. O
[`validate_documentary_observations.py`](../../scripts/validate_documentary_observations.py)
reconstrói o pacote a partir do PDF original, exige sua identidade, cobre
todos os IDs selecionados e confere cada trecho literalmente na página do
documento vinculado. Ele não verifica se a frase interpretativa do agente é
verdadeira, se o PDF visual confirma o texto extraído, nem se a prova é
admissível ou suficiente. Um ensaio no Codex com PDF inteiramente fictício
produziu saída validada, mas a variante não foi despachada em processo real
nem vinculada ao manifesto; faltam revisão jurídica e validação com fontes de
caso autorizado.

O adaptador [`build_documentary_work_records.py`](../../scripts/build_documentary_work_records.py)
revalida a fonte e a rota probatória antes de derivar apenas os registros de
custódia já previstos pela trilha condicional. Exige todas as evidências do
pedido; uma lacuna gera `insufficient` e recibo `gap`. Mesmo com citações
válidas, mantém `assessment` vazio e `pending_human_review`. O ensaio Codex
publica esses dois registros como **fragmentos**, não como artefatos completos
do pipeline; pesquisa jurídica e demais trabalhos continuam independentes.
