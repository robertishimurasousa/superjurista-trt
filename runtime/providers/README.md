# Contratos de interface dos provedores

`interfaces.json` define a interface independente do ambiente para obtenção
de processos e pesquisa jurídica em fontes autorizadas. Provedores concretos
implementam os protocolos Python e registros imutáveis de requisição e
resposta em `scripts/provider_interfaces.py`.

O núcleo compartilhado conhece apenas capacidades e dados validados. URLs do
tribunal, autenticação, cookies, cabeçalhos, nomes de tarefas e formatos de
requisição específicos da fonte pertencem aos adaptadores e perfis concretos.

## Interfaces

- `pje_case_acquisition`: validação da sessão, descoberta de processos,
  indexação paginada, download e conferência SHA-256 dos documentos;
- `legal_research`: pesquisa paginada, obtenção da fonte, endereço HTTPS
  oficial, estado e metadados da custódia literal.

## Limite da conformidade

A suíte com provedores simulados exercita as duas interfaces usando código de
tribunal diferente do alvo inicial. Isso comprova que o executor compartilhado
não depende de constante regional. Não comprova autenticação, alcance,
autorização nem compatibilidade operacional de um provedor real.

```bash
python3 -m unittest tests.test_provider_interfaces -v
```

Adaptadores reais do PJe-JT e da pesquisa são pacotes separados e exigem
evidência autorizada e sanitizada antes de implementação ou aceite.

## Segmentar e classificar PDF consolidado e autorizado do PJe

`scripts/segment_pje_pdf.py` usa os destinos do sumário nativo incorporado
ao PDF consolidado exportado pelo PJe. Deriva IDs estáveis `DOC-NNN`, datas,
referências do provedor e intervalos inclusivos de páginas sem ler o texto dos
autos. Os segmentos alimentam o classificador trabalhista compartilhado, cuja
saída exclui intencionalmente títulos do provedor, referências e conteúdo.

Ambos os artefatos de saída contêm metadados do processo e devem ficar em
diretório protegido fora do repositório. O comando rejeita saída no repositório
e não sobrescreve artefato existente:

```bash
mkdir -p /protected/case/classification
chmod 700 /protected/case/classification
python3 scripts/segment_pje_pdf.py \
  --input /protected/case/process.pdf \
  --output /protected/case/classification
```

O comando grava `document-segments.json` e `document-classification.json` com
permissão `0600`. PDFs sem sumário PJe completo e ordenado são rejeitados; não
são divididos heuristicamente pelo OCR. Certidões, avisos e rótulos ambíguos
permanecem `unknown` até haver tipo semanticamente adequado na taxonomia e
evidência aprovada de revisão.

Execute a suíte sintética de segmentação e classificação com:

```bash
python3 -m unittest tests.test_pje_pdf_segmentation -v
```

## Consultar a fonte oficial de jurisprudência do TST

`scripts/tst_official_adapter.py` implementa `legal_research` para a aplicação
pública de jurisprudência do TST. Usa o serviço indicado pela configuração do
portal oficial, restringe requisições e redirecionamentos a
`jurisprudencia-backend.tst.jus.br`, limita respostas e emite artefato
`precedent-corpus` válido conforme esquema.

Um número CNJ exato usa o filtro estruturado `numeracaoUnica` do TST; outras
entradas são consultas textuais. O adaptador verifica se o trecho normalizado
consta do HTML integral oficial antes de aceitar a fonte. Não infere se a
decisão continua precedente vinculante vigente, pois a resposta não traz
campo normalizado de validade; o estado permanece `unknown` e exige revisão
humana.

Gere um corpus limitado fora do repositório:

```bash
python3 scripts/tst_official_adapter.py \
  --query '0021532-54.2015.5.04.0006' \
  --output /tmp/tst-precedent-corpus.json \
  --tribunal-code TRT12 \
  --limit 1 \
  --page-size 1
```

O artefato pode conter texto judicial público. Revise-o conforme a política
de dados antes de movê-lo para dados de teste versionados. Testes unitários
usam registros sintéticos e não acessam a rede:

```bash
python3 -m unittest tests.test_tst_official_adapter -v
```

## Consultar jurisprudência oficial do PJe do TRT12

`scripts/trt12_official_adapter.py` implementa `legal_research` para a fonte
TRT12 indicada pelo perfil. O portal atual delega a pesquisa do primeiro e
segundo graus ao repositório oficial Falcão. O adaptador fixa o filtro em
`TRT12`, consulta as coleções `sentencas` e `acordaos` em conjunto, pagina de
forma limitada a partir de zero e obtém o documento selecionado novamente pelo
endpoint de detalhes da coleção antes de aceitar sua custódia literal.

A cobertura é explícita: Falcão é a fonte atual apoiada no PJe, e o portal
informa documentos de 2016 em diante. Coleções físicas e Provi mais antigas,
descritas em material histórico, não estão expostas pelo portal atual. Por
isso, cada fonte normalizada registra cobertura `current_pje` e lacuna de
cobertura legada. Sentenças recebem âmbito `trt12_first_instance`; acórdãos,
`trt12_second_instance`. Nenhum recebe estado vinculante ou de vigência que
a resposta oficial não forneça.

A aplicação pública estabelece sessão de curta duração e limita consultas.
Uma resposta de limite de consultas bloqueia e só pode ser repetida após a
janela oficial. A inicialização da sessão atualmente retorna lista no
endpoint de notificações e objeto no preenchimento automático; o transporte
valida os formatos por endpoint antes da pesquisa.

Gere corpus público limitado fora do repositório:

```bash
python3 scripts/trt12_official_adapter.py \
  --query 'horas extras' \
  --output /tmp/trt12-jurisprudence-corpus.json \
  --tribunal-code TRT12 \
  --limit 2 \
  --page-size 5
```

Execute a suíte de contrato e normalização sem rede:

```bash
python3 -m unittest tests.test_trt12_official_adapter -v
```

## Consultar precedentes regionais oficiais do TRT12

`scripts/trt12_precedent_adapter.py` implementa `legal_research` para os
precedentes regionais do TRT12. Combina o acompanhamento de IRDR vinculado
pelo portal de uniformização com a página de teses do tribunal. O adaptador
usa endereços HTTPS exatos e limitados, rejeita redirecionamentos ou formatos
de página inesperados e relê a publicação oficial ao obter a fonte escolhida.

Registros de IRDR preservam questão submetida, tese publicada, estado do
acompanhamento e alcance da suspensão. Tese publicada é `current` salvo
cancelamento expresso na fonte. Incidente admitido sem tese é `pending` ou
`stayed` quando o acompanhamento indica suspensão ativa. Texto sobre
suspensão histórica permanece anotação após a publicação da tese, sem virar
suspensão atual.

A página oficial informa atualmente que não houve fixação de tese em IAC. O
adaptador expõe essa informação por `coverage()` e não fabrica precedente IAC.
Teses IUJ publicadas são normalizadas como orientações regionais, inclusive
com marcadores explícitos de cancelamento.

Gere corpus limitado fora do repositório:

```bash
python3 scripts/trt12_precedent_adapter.py \
  --query 'horas extras' \
  --output /tmp/trt12-precedent-corpus.json \
  --tribunal-code TRT12 \
  --limit 5
```

O artefato contém texto jurídico público e deve passar pela política de dados
antes de virar dado de teste versionado. Execute a suíte sem rede de contrato,
formato da fonte, estado, suspensão, cobertura IAC e corpus com:

```bash
python3 -m unittest tests.test_trt12_precedent_adapter -v
```

## Consolidar corpus de precedentes oficiais

`scripts/consolidate_precedents.py` reúne um ou mais artefatos
`precedent-corpus` válidos sem descartar a origem. Ordena fontes de forma
determinística por tipo: vinculante, qualificada, normativa, súmula,
orientação, jurisprudência e jurisprudência persuasiva.

Fontes equivalentes compartilham origem, referência normalizada e tese. O
registro mais bem classificado torna-se canônico; o relatório auxiliar
preserva ID, URL oficial e resumo SHA-256 do trecho literal de cada duplicata.
IDs repetidos com conteúdo alterado bloqueiam. Estado `unknown` nunca
substitui evidência explícita; estados explícitos divergentes geram
`conflicting` e registro estruturado para decisão humana.

Questão jurídica e tese devem constar do trecho literal. Esse controle de
custódia impede manter conclusão normalizada sem a citação que a sustenta.

```bash
python3 scripts/consolidate_precedents.py \
  --input /tmp/tst-precedent-corpus.json \
  --input /tmp/trt12-precedent-corpus.json \
  --output /tmp/consolidated-precedent-corpus.json \
  --report-output /tmp/consolidated-precedent-custody.json
```

Execute a suíte determinística de consolidação com:

```bash
python3 -m unittest tests.test_precedent_consolidation -v
```

## Avaliar observação sanitizada da sessão

`pje-session-contract.json` define estados neutros para verificar sessões.
Um adaptador concreto pode informar somente estado HTTP, marcadores semânticos
reconhecidos e nomes de cookies ou cabeçalhos, nunca valores de credenciais.
`scripts/pje_session_adapter.py` valida capacidade e tribunal alvo e
classifica a observação como `valid`, `expired`, `mfa_required`,
`unauthorized` ou `unknown`.

Marcadores conflitantes e respostas autenticadas sem evidência de sessão
reconhecida resultam em `unknown`. HTTP 401 e 403 resultam em `unauthorized`
mesmo com marcador de autenticação. O classificador não faz login, não gera
MFA e não conhece endpoint de tribunal.

```bash
python3 -m unittest tests.test_pje_session_adapter -v
```

O ensaio sintético TRT99 comprova contrato de estados e saída sem segredos. A
verificação real do TRT12 ainda depende do mapa `PJE-01` autorizado e revisado.

## Descobrir tarefas e filas de processos autorizadas

`pje-task-discovery-contract.json` define outra interface neutra para
descoberta paginada de tarefas e processos. Adaptadores concretos normalizam
respostas em IDs estáveis de tarefas, nomes, números CNJ e unidades judiciais.
`scripts/pje_task_discovery.py` controla cursores, duplicatas por tarefa,
região do tribunal, ordem determinística e saída sem segredos.

```bash
python3 -m unittest tests.test_pje_task_discovery -v
```

Fila autorizada vazia é resultado válido e completo. Cursores repetidos,
páginas incompletas sem cursor, tarefas ou processos duplicados e regiões CNJ
divergentes bloqueiam. O provedor simulado TRT99 prova apenas comportamento
compartilhado; nomes de tarefas, endpoints, dados e cursores reais do TRT12
ainda exigem o mapa `PJE-01` revisado.

## Obter documentos verificados e retomar a obtenção

`scripts/acquire_pje_documents.py` monta o índice normalizado completo antes
de baixar todos os documentos ou subconjunto explícito. Cada conteúdo aceito
deve corresponder ao SHA-256 publicado no índice. IDs solicitados ausentes e
indisponibilidade limitada do provedor permanecem lacunas estruturadas.

`scripts/recover_pje_acquisition.py` adiciona checkpoint atômico e versionado
ao contrato. Persiste somente identidade normalizada do processo, resumo do
alcance da autorização, resumos do catálogo e conteúdo, número limitado de
tentativas e caminhos locais canônicos. Na retomada, confere o conteúdo aceito
antes de acessar o provedor, não o baixa novamente e bloqueia alterações do
catálogo, requisição, limite de tentativas ou bytes locais. O limite é de uma
a cinco tentativas e não pode ser ampliado por parâmetros diferentes.

Execute as suítes sem rede de obtenção e recuperação com:

```bash
python3 -m unittest \
  tests.test_pje_document_acquisition \
  tests.test_pje_recovery \
  -v
```

Os dados de teste usam TRT99 e provam apenas recuperação compartilhada. O
aceite de `PJE-05` ainda exige ensaios fechados e autorizados repetidos do
TRT12 com êxito mínimo de 95%; nenhum ensaio sintético compõe essa taxa.

## Montar mapa HAR sanitizado

HARs brutos e sessões extraídas ficam locais e ignorados pelo Git. Para uma
captura autorizada, monte mapa determinístico que preserva a estrutura dos
endpoints, mas remove valores de cabeçalhos, cookies e consultas, corpos das
requisições e respostas e IDs dinâmicos do caminho:

```bash
python3 scripts/sanitize_pje_har.py \
  --input /path/outside-the-repository/authorized-capture.har \
  --output tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1 \
  --authorized-capture
```

O sinalizador de reconhecimento registra declaração do operador, não prova
independente da autorização. Revise o mapa gerado antes de prepará-lo para
commit. Nunca copie HAR bruto nem sessão gerada para o repositório.

Valide integridade estrutural e cobertura antes da revisão humana:

```bash
python3 scripts/validate_pje_har_map.py \
  --map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1
```

Código de saída `0` significa cobertura técnica suficiente para revisão
humana; `1` informa lacunas explícitas; `2` rejeita mapa inválido, incoerente
ou adulterado. Prontidão técnica não é aceite jurídico ou operacional. Não
provoque falha de autenticação, tempo esgotado ou erro do provedor apenas para
enriquecer a captura. Falta de endpoints funcionais ou de artefatos de
autenticação bloqueia; grupos de falha não observados naturalmente retornam
em `observed_failure_gaps` e seguem como limitações explícitas dos ensaios de
sessão e recuperação.
