# Plano arquitetural: SuperJurista TRT12 — primeiro grau

**Situação:** aprovado
**Versão:** 0.17.0
**Data:** 2026-09-21
**Alvo principal:** sentenças trabalhistas do primeiro grau do TRT12
**Alvos futuros:** segundo grau do TRT12 e, depois, outros Tribunais Regionais do Trabalho
**Acompanhamento do avanço:** [`superjurista-trt12-ROADMAP.md`](../roadmaps/superjurista-trt12-ROADMAP.md)

---

## 1. Decisão principal

O projeto preservará o núcleo determinístico de execução do SuperJurista e
substituirá a camada de domínio específica da Justiça Federal por uma camada
voltada à Justiça do Trabalho.

Claude Code e Codex são ambientes de execução previstos. Ambos devem consumir
o mesmo domínio jurídico, contratos de artefatos, perfil de tribunal, conjunto
de scripts determinísticos e testes de aceite. Arquivos específicos de cada
ambiente podem orquestrar o trabalho, mas não criar regras jurídicas divergentes.

O primeiro alvo com formato de produção é o **primeiro grau do TRT12**. O
segundo grau e outros TRTs são possibilidades de extensão, não afirmações de
compatibilidade atual. A arquitetura deve prever os pontos de extensão desde
já, enquanto implementação e validação avançam nesta ordem:

1. primeiro grau do TRT12;
2. segundo grau do TRT12;
3. um TRT adicional para comprovar a portabilidade;
4. suporte mais amplo a outros TRTs somente após essa comprovação.

Isso evita dois erros:

- fixar regras do TRT12 em capacidades jurídicas que devem ser reutilizáveis;
- generalizar prematuramente comportamentos não observados em outro tribunal.

---

## 2. Objetivo

Construir um sistema auditável, retomável e supervisionado por pessoas que
receba um processo PJe-JT autorizado do primeiro grau do TRT12, extraia e
estruture os autos, mapeie cada pedido e defesa, encaminhe questões jurídicas
e probatórias, pesquise precedentes em fontes de autoridade, redija uma proposta
de sentença trabalhista e valide o resultado por verificações determinísticas
em Claude Code e Codex.

O resultado é uma **minuta para revisão judicial**, nunca decisão autônoma.

### 2.1 Entrada principal

- um espaço de trabalho autorizado com processo do PJe-JT; ou
- um espaço de trabalho de processo previamente baixado e higienizado, com
  índice de documentos e arquivos de origem.

### 2.2 Saída principal

```text
data/judgment/<CNJ_NUMBER>/<CNJ_NUMBER>-labor-judgment.md
```

O espaço de trabalho também preserva artefatos intermediários, a origem das
evidências e dos precedentes, os resultados das verificações e o manifesto
de execução.

### 2.3 Critério de sucesso

O produto mínimo de primeiro grau só terá sucesso quando processar de forma
reproduzível a amostra histórica aprovada e satisfizer todos os critérios críticos:

- todo pedido formulado consta da matriz de pedidos;
- todo pedido controvertido recebe rota de análise probatória e/ou jurídica;
- todo item do dispositivo corresponde a pedido formulado ou questão
  expressamente identificada que o juízo possa apreciar;
- toda citação literal externa tem fonte autorizada rastreável;
- a revisão cega não encontra defeito jurídico ou fático crítico remanescente;
- o pipeline retoma sem ignorar silenciosamente artefatos inválidos ou antigos.

---

## 3. Escopo

### 3.1 Incluído no produto mínimo do primeiro grau do TRT12

- perfil do primeiro grau do TRT12;
- sessão do PJe-JT, lista de tarefas, descoberta de processos, índice e download
  de documentos;
- classificação de documentos trabalhistas;
- linha do tempo processual e relatório trabalhista;
- matrizes de pedidos, defesas, evidências e providências requeridas;
- encaminhamento por pedido para pesquisa jurídica, análise probatória,
  revisão de cálculos e revisão processual;
- pesquisa de precedentes do TST, STF/BNP e TRT12 e de jurisprudência do TRT12;
- análise jurídica por pedido;
- redação de minuta de sentença trabalhista e consolidação determinística;
- verificações de congruência, citações, fontes, critérios de cálculo e
  integridade final;
- validação histórica cega e dossiê de preparação do piloto controlado.

### 3.2 Explicitamente fora do primeiro produto mínimo

- protocolo, assinatura, publicação ou movimentação autônoma no PJe-JT;
- substituição da revisão judicial;
- votos ou decisões do segundo grau do TRT12;
- declaração de compatibilidade com outro TRT sem validação específica;
- liquidação monetária automatizada apresentada como equivalente ao PJe-Calc;
- treinamento ou ajuste fino de modelos;
- processamento de processos sigilosos sem protocolo aprovado de tratamento de dados.

### 3.3 Escopo futuro

- análise de recursos e redação de votos no segundo grau do TRT12;
- importação/exportação com PJe-Calc ou interoperabilidade de cálculos verificada
  independentemente;
- perfis de outros TRTs;
- adaptadores reutilizáveis quando pelo menos dois TRTs demonstrarem o mesmo
  contrato técnico.

---

## 4. Princípios orientadores

1. **Um alvo validado por vez.** O primeiro grau do TRT12 é o único alvo
   executável na primeira etapa de entrega.
2. **Separação entre núcleo e perfil.** Agentes reutilizáveis não podem conter
   URLs, unidades judiciárias, órgãos julgadores locais ou constantes de
   autenticação do TRT12.
3. **Análise por pedido.** O processo trabalhista não é uma questão indivisível.
   Cada pedido é uma unidade decisória rastreável.
4. **O arquivo representa o estado.** Agentes gravam artefatos e retornam uma
   linha de situação.
5. **Verificações, não declarações de confiança.** A conclusão depende de scripts
   e evidências de revisão.
6. **Rejeição por segurança.** Evidência ausente, ilegível, antiga ou incoerente
   impede o avanço.
7. **Sem citação sem origem.** Citações literais exigem entrada em conjunto de
   fontes autorizado.
8. **Sem substituição jurídica silenciosa.** Decisão persuasiva não pode receber
   o rótulo de vinculante.
9. **A decisão humana é obrigatória.** O sistema propõe; o magistrado decide.
10. **A expansão deve ser comprovada.** Suporte a múltiplos TRTs exige
    implementação de um segundo TRT e evidências de regressão.
11. **Independência do ambiente.** Claude Code e Codex podem usar sintaxes
    diferentes de orquestração, mas devem produzir os mesmos artefatos
    versionados e passar nas mesmas verificações.

### 4.1 Política de migração com prioridade ao reuso

Esta é uma migração do fork existente, não uma reescrita do zero. O repositório
atual é a base de implementação. Antes de substituir componentes, é preciso
inventariá-los, caracterizá-los e atribuir um dos quatro tratamentos:

| Tratamento | Significado | Evidência exigida |
|---|---|---|
| Preservar | O comportamento independe do tribunal e permanece essencialmente igual | Caracterização e regressão passam para o comportamento existente |
| Adaptar | O núcleo é reutilizável, mas contém premissas da Justiça Federal | Testes protegem a parte reutilizável e casos TRT12 comprovam a adaptação |
| Substituir | O contrato ou comportamento jurídico é incompatível com a Justiça do Trabalho | O substituto passa em critérios iguais ou mais fortes antes de retirar o caminho antigo |
| Retirar | A capacidade está fora do escopo do primeiro grau do TRT12 | Análise de dependências mostra que nenhum fluxo TRT12 aceito ainda a exige |

Nenhum componente deve ser reescrito apenas para deixar a arquitetura mais
elegante. A substituição requer regra jurídica incompatível, contrato de
provedor ou de dados incompatível, requisito de segurança ou defeito de
manutenção demonstrado. A implementação antiga permanece disponível até a
adaptação ou substituição passar no critério de aceite.

### 4.2 Mapa inicial de tratamento do fork

O mapa seguinte é uma hipótese de planejamento. O item `FND-04` do roteiro
deve confirmá-la no código e registrar o tratamento definitivo por arquivo.

| Capacidade existente no fork | Tratamento inicial | Tratamento no TRT12 |
|---|---|---|
| Orquestrador cego, arquivo como estado, resposta do agente em uma linha e limite de tentativas | Preservar | Manter o modelo de execução e acrescentar cobertura de regressão |
| Retomada e padrão de verificações determinísticas | Preservar e fortalecer | Reusar o padrão de `verificar_sentenca.py` e verificações relacionadas; versionar dependências dos artefatos |
| Consolidação determinística de fontes e sentença | Preservar e adaptar | Manter a consolidação sem modelo de linguagem e a rastreabilidade; mudar contratos de artefatos trabalhistas |
| Rastreabilidade de citações e conferência literal | Preservar e adaptar | Manter a rejeição por segurança; registrar tipos de fonte do TST e TRT12 |
| Conversão de PDF e OCR | Preservar e fortalecer | Caracterizar casos digitais e digitalizados; corrigir portabilidade de execução e dependências quando necessário |
| Linha do tempo processual | Adaptar | Preservar a extração cronológica; incluir eventos e vocabulário trabalhistas |
| Relator do processo | Adaptar | Preservar a referência à fonte; substituir o vocabulário federal por cobertura de pedidos trabalhistas |
| Análise documental, testemunhal, pericial, digital, confissão e reconhecimento | Adaptar após auditoria | Manter raciocínio probatório genérico apenas onde casos demonstram ausência de premissas federais |
| Consolidação de pesquisa e revisão de fontes | Adaptar | Preservar hierarquização e rastreabilidade; implementar hierarquia de autoridades trabalhistas |
| Download atual do PJe | Adaptar por interface | Reusar sessão e download somente após captura HAR autorizada do TRT12 demonstrar compatibilidade |
| Agentes e provedores federais, como CJF, TNU, JULIA/TRF5 e pesquisa STJ específica da Justiça Federal | Retirar do caminho executável TRT12 | Manter fora do pipeline trabalhista aceito; substituir por adaptadores TST/TRT12 e rotas STF/BNP aplicáveis |
| Agentes de listas de julgamento dos TRFs e regras de revisão exclusivamente federais | Retirar do primeiro grau do TRT12 | Não apagar antes de comprovar, por dependências, que o perfil TRT12 não os alcança |
| Premissas federais de mérito, cálculos, remessa, honorários e redação | Substituir ou adaptar profundamente | Implementar análise por pedido, critérios trabalhistas de cálculo, congruência e redação de sentença |
| Perfis de tribunal, matriz trabalhista, roteador de questões, pesquisa TST/TRT12 e matriz de dispositivo | Criar | São contratos ausentes exigidos pelo alvo TRT12 |

### 4.3 Sequência da migração

1. Congelar um conjunto representativo de casos e saídas do fork atual.
2. Acrescentar testes de caracterização para capacidades marcadas como preservar ou adaptar.
3. Introduzir interfaces estáveis de núcleo e provedores em torno do comportamento existente.
4. Adaptar uma fatia vertical para o TRT12: obter, converter, classificar,
   relatar, analisar, redigir e verificar.
5. Comparar saídas antigas e novas onde as responsabilidades se sobrepõem.
6. Retirar um caminho antigo somente após o caminho TRT12 ser aceito e as
   verificações de dependências passarem.

Essa sequência evita uma reescrita de uma vez só e torna o reuso mensurável.

---

## 5. Arquitetura pretendida

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                       ADAPTADORES DE EXECUÇÃO                               │
│                  Claude Code                 Codex                           │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ manifesto de execução compartilhado
┌──────────────────────────────────────────────────────────────────────────────┐
│                         NÚCLEO DETERMINÍSTICO                                │
│ orquestração · retomada · manifestos · verificações · consolidação · auditoria│
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ contratos estáveis
┌───────────────────────────────▼──────────────────────────────────────────────┐
│                      DOMÍNIO TRABALHISTA                                     │
│ pedidos · evidências · encaminhamento · análise jurídica · minuta           │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ interfaces de provedores
             ┌──────────────────┼──────────────────┐
             │                  │                  │
┌────────────▼───────────┐ ┌────▼────────────┐ ┌──▼───────────────────────────┐
│ Adaptador PJe-JT       │ │ Pesquisa        │ │ Adaptadores de cálculo      │
│ sessão/índice/download │ │ TST/TRT12/BNP   │ │ critérios/revisão PJe-Calc  │
└────────────┬───────────┘ └────┬────────────┘ └──┬───────────────────────────┘
             │                  │                  │
┌────────────▼──────────────────▼──────────────────▼───────────────────────────┐
│                           PERFIL DO TRT                                      │
│ TRT12 · primeiro grau · URLs · fontes · assinatura · regras locais            │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Regra de extensão

Uma extensão pode fornecer configurações e implementações de adaptadores, mas
não pode bifurcar nem copiar os contratos centrais de pedidos e evidências. Se
um novo TRT exigir outro contrato, ele deve ser generalizado no núcleo e
testado novamente contra o TRT12.

### 5.2 Contrato para dois ambientes de execução

A definição canônica das capacidades é independente do ambiente de execução. Os adaptadores
para Claude Code e Codex podem traduzir nomes de ferramentas, distribuição de tarefas,
relato de progresso e descoberta de habilidades, mas não podem duplicar nem alterar o
prompt jurídico, o esquema dos artefatos, o perfil do tribunal ou a lógica dos controles.

| Aspecto | Contrato compartilhado | Adaptador Claude Code | Adaptador Codex |
|---|---|---|---|
| Instruções do projeto | Políticas jurídicas e de engenharia | Projeção em `CLAUDE.md` | Projeção em `AGENTS.md` |
| Habilidades | Instruções e recursos canônicos | Local compatível com Claude | Projeção em `.agents/skills` |
| Orquestração | Manifesto versionado do fluxo e dependências entre etapas | Despacho por comandos/tarefas do Claude | Despacho por tarefas/ferramentas do Codex |
| Progresso | Manifesto de artefatos e estado dos controles | Visão de progresso do ambiente | Visão de progresso do ambiente |
| Ferramentas | Nomes de capacidades e esquemas de entrada/saída | Vínculos de ferramentas do Claude | Vínculos Codex/MCP ou locais |
| Validação | Scripts, casos de teste e critérios de aceite compartilhados | Executa a suíte compartilhada | Executa a suíte compartilhada |

Não se exige que os dois modelos produzam textos idênticos byte a byte. Conformidade entre
ambientes significa produzir artefatos válidos conforme os esquemas, preservar a custódia das
fontes, respeitar as mesmas condições de bloqueio seguro e passar pelos mesmos controles
determinísticos e de revisão humana.

### 5.3 Contrato de interface dos provedores

A obtenção de dados do PJe e a pesquisa jurídica usam interfaces versionadas por capacidade
em `runtime/providers/`. O núcleo compartilhado controla requisições e respostas imutáveis,
segurança da paginação, integridade do conteúdo e custódia das fontes oficiais. Os adaptadores
concretos controlam endpoints, autenticação, tradução dos dados do provedor e comportamento
específico do tribunal.

A conformidade é exercitada com provedores simulados e código de um tribunal não alvo. Isso
protege a separação entre núcleo e perfil, mas não certifica acesso real ao PJe-JT nem às
fontes de pesquisa.

### 5.4 Limite da captura autorizada

Capturas HAR brutas e sessões extraídas são insumos operacionais locais e não podem se tornar
artefatos do repositório. O processamento da evidência produz um mapa determinístico e
sanitizado de endpoints. Ele conserva métodos, modelos de endpoint, nomes de cabeçalhos e
cookies, estado da resposta, tipo de conteúdo, classificação da capacidade e estados de
falha. Remove valores de cabeçalhos, cookies e parâmetros de consulta, corpos de requisição
e resposta e identificadores dinâmicos reconhecidos nos caminhos.

O reconhecimento pelo operador é obrigatório antes de processar uma captura, mas não constitui
prova independente de autorização. `PJE-01` ainda exige uma captura autorizada do TRT12 e
revisão humana do mapa resultante.

O controle de revisão do mapa confere o resumo criptográfico sanitizado, tribunal e instância
alvo, contagens de endpoints e cobertura, coerência dos estados de falha, modelos de caminho
expurgados, artefatos de autenticação e cobertura mínima de capacidades e falhas. A ausência
de evidência é relatada como pendência; violações estruturais ou de custódia bloqueiam o fluxo.

### 5.5 Limite do estado da sessão

A obtenção de credenciais e a classificação do estado da sessão são responsabilidades
separadas. Um adaptador do tribunal pode verificar uma sessão já autorizada, mas o
classificador compartilhado recebe apenas um estado HTTP sanitizado, marcadores semânticos
reconhecidos e nomes de cookies ou cabeçalhos. Ele nunca recebe nem emite valores de
credenciais, material de MFA ou corpos de requisição ou resposta.

O contrato versionado reconhece `valid`, `expired`, `mfa_required`, `unauthorized` e
`unknown`. Uma negativa HTTP prevalece sobre marcadores otimistas. Marcadores contraditórios
ou um marcador de autenticação sem evidência reconhecida de sessão resultam em `unknown` por
segurança. Testes sintéticos com TRT99 comprovam esse comportamento compartilhado; não
comprovam autenticação real no TRT12. A verificação concreta do TRT12 continua dependente do
mapa `PJE-01` autorizado e revisado.

### 5.6 Limite da descoberta de tarefas e processos

O executor compartilhado de descoberta solicita a um adaptador concreto apenas páginas
normalizadas e autorizadas de tarefas e processos. Ele controla paginação limitada, detecção
de cursores repetidos, eliminação de duplicatas de tarefas e processos por tarefa, validação
da região do tribunal no número CNJ, ordenação determinística e saída sem segredos. Uma fila
autorizada vazia é um resultado completo, não um erro.

Identificadores e nomes de tarefas, endpoints, campos do provedor e formatos de cursor
continuam sob responsabilidade do adaptador. Os scripts originais de listagem do TRF5 são
evidência para reaproveitamento, não uma descrição do TRT12. Os testes sintéticos com TRT99
comprovam o contrato portável; o adaptador concreto do TRT12 ainda depende do mapa `PJE-01`
revisado.

---

## 6. Contrato do perfil do tribunal

Caminhos canônicos:

```text
runtime/profiles/
├── schema.json
├── registry.json
└── trt12.json
```

O esquema é um JSON Schema padrão, independente do ambiente de execução. O registro relaciona
segmentos judiciários, contratos de adaptadores dos sistemas processuais, fontes de pesquisa
e referências oficiais sem inserir valores do TRT12 no esquema central. O perfil contém os
valores específicos do tribunal:

- segmento da Justiça do Trabalho, TRT12, região 12, Santa Catarina e dígito 5 do ramo CNJ;
- primeiro grau habilitado, com `labor_judgment` como artefato final;
- segundo grau descrito para compatibilidade futura, mas expressamente desabilitado;
- PJe-JT como sistema processual, com apenas o adaptador do primeiro grau declarado;
- TST, BNP, STF e TRT12 como fontes oficiais de pesquisa;
- revisão humana obrigatória e preservação literal das fontes; e
- protocolo externo, assinatura e publicação desabilitados.

Entradas do registro com `contract_status: declared` definem a interface de adaptador
esperada pelos próximos pacotes. Não afirmam que o adaptador foi implementado, autenticado ou
verificado operacionalmente.

A validação do perfil deve rejeitar:

- dígitos desconhecidos do ramo CNJ;
- instâncias habilitadas sem adaptador;
- conjuntos vazios de assinaturas;
- fontes de pesquisa sem adaptador registrado;
- qualquer política que permita protocolo, assinatura ou publicação no MVP.

---

## 7. Contratos estáveis de dados

Os contratos abaixo são implementados como arquivos JSON Schema versionados em
`runtime/contracts/schemas/`. `runtime/contracts/catalog.json` seleciona a versão vigente;
`runtime/contracts/VERSIONING.md` define a política de migração com bloqueio seguro. Os
agentes só podem consumir artefatos que passem no validador compartilhado e estejam na versão
vigente do contrato.

### 7.0 `document-classification.json`

Cada documento baixado recebe um tipo estável do domínio trabalhista ou um estado explícito
de desconhecimento/conflito. A base determinística registra apenas a evidência da regra e
nunca copia o texto-fonte para o artefato de classificação.

```json
{
  "schema_version": 2,
  "classifier_version": 2,
  "documents": [
    {
      "document_id": "DOC-001",
      "document_type": "initial_pleading",
      "classification_status": "classified",
      "matched_rule_ids": ["initial-pleading"],
      "reason_code": "matched_rule"
    }
  ]
}
```

O classificador de relevância do fork original é evidência para reaproveitar a normalização
determinística e o tratamento explícito de desconhecidos. Seus rótulos e pressupostos de
prioridade da Justiça Federal não passam à taxonomia trabalhista sem evidência de calibração.

### 7.1 `labor-report.json`

O relatório processual é um artefato estruturado de referência. Podem-se gerar visualizações
narrativas a partir dele, mas elas não substituem os vínculos com as fontes nem as lacunas
para revisão.

```json
{
  "schema_version": 1,
  "case_context": {"case_number": "0000000-00.2026.5.12.0000"},
  "parties": [
    {
      "party_id": "PTY-001",
      "role": "claimant",
      "display_name": "...",
      "source_document_id": "DOC-001",
      "source_locator": "page 1"
    }
  ],
  "procedural_phase": {
    "phase": "knowledge",
    "status": "identified",
    "source_document_id": "DOC-001",
    "source_locator": "page 1"
  },
  "timeline": [],
  "positions": [],
  "review_gaps": []
}
```

A montagem determinística rejeita referências fora do manifesto de documentos, preserva fase
desconhecida e posições ausentes como lacunas para revisão e ordena os identificadores
estáveis independentemente do ambiente de execução ou da ordem de entrada.

### 7.2 `case-context.json`

```json
{
  "schema_version": 1,
  "case_number": "0000000-00.2026.5.12.0000",
  "court": "TRT12",
  "instance": 1,
  "phase": "knowledge",
  "procedure": "ordinary",
  "court_unit": "Labor Court",
  "confidentiality": "public_or_authorized",
  "source_manifest": "document-index.json"
}
```

### 7.3 `claim-matrix.json`

Cada pedido formulado recebe um identificador estável.

```json
{
  "schema_version": 1,
  "taxonomy_version": 1,
  "claims": [
    {
      "claim_id": "CLM-001",
      "label": "overtime",
      "claimant_position": {
        "summary": "...",
        "source_document_id": "DOC-001",
        "source_locator": "pages 4-5"
      },
      "respondent_positions": [
        {
          "defense_id": "DEF-001",
          "respondent_party_id": "PTY-002",
          "summary": "...",
          "source_document_id": "DOC-002",
          "source_locator": "pages 2-3"
        }
      ],
      "requested_remedies": ["overtime_payment"],
      "contested_facts": [],
      "legal_issues": [],
      "status": "mapped",
      "review_gaps": []
    }
  ]
}
```

As posições do reclamante e de cada defesa mantêm localizadores independentes para que
múltiplos reclamados não sejam fundidos. Divergências na taxonomia e pedidos, providências
requeridas ou defesas ausentes exigem revisão; não podem ser normalizados silenciosamente.

### 7.4 `evidence-matrix.json`

```json
{
  "schema_version": 1,
  "evidence_items": [
    {
      "evidence_id": "EVD-001",
      "claim_ids": ["CLM-001"],
      "type": "time_record",
      "source_document_id": "DOC-014",
      "source_locator": "page_or_event_reference",
      "proposition": "...",
      "relation": "supports_claim",
      "limitations": [],
      "analysis_status": "pending",
      "conflicts_with_evidence_ids": []
    }
  ],
  "uncovered_claim_ids": []
}
```

Os vínculos de contradição são simétricos; vínculos a si mesmos ou a destinos inexistentes
bloqueiam o fluxo. Todo pedido sem prova vinculada permanece explícito em
`uncovered_claim_ids`.

### 7.5 `issue-route.json`

```json
{
  "schema_version": 1,
  "routes": [
    {
      "claim_id": "CLM-001",
      "route_status": "routed",
      "requires_legal_research": true,
      "requires_evidence_analysis": true,
      "requires_calculation_review": true,
      "requires_procedural_review": false,
      "research_questions": [],
      "evidence_questions": [],
      "route_reason": "...",
      "abstention_reasons": []
    }
  ]
}
```

Cada pedido conhecido possui exatamente um encaminhamento. Um encaminhamento sem trilha
habilitada só é válido como resultado explícito `abstained`, com um ou mais motivos; pedidos
encaminhados não podem conter motivos de abstenção. As trilhas jurídica e probatória exigem
perguntas concretas para o trabalho posterior.

### 7.6 `precedent-corpus.json`

```json
{
  "schema_version": 1,
  "sources": [
    {
      "source_id": "TST-001",
      "origin": "TST",
      "type": "qualified_precedent",
      "reference": "...",
      "status": "current",
      "binding_scope": "national_labor_justice",
      "legal_question": "...",
      "holding": "...",
      "verbatim_excerpt": "...",
      "official_url": "...",
      "retrieved_at": "ISO-8601"
    }
  ]
}
```

### 7.7 `claim-analysis.json`

```json
{
  "schema_version": 1,
  "analyses": [
    {
      "analysis_id": "ANL-001",
      "claim_id": "CLM-001",
      "facts_found": [],
      "evidence_ids": [],
      "evidence_assessment": [],
      "applicable_rules": [],
      "precedent_source_ids": [],
      "reasoning": "...",
      "proposed_outcome": "pending_human_review",
      "limitations": []
    }
  ]
}
```

### 7.8 `disposition-matrix.json`

```json
{
  "schema_version": 1,
  "items": [
    {
      "disposition_id": "DSP-001",
      "claim_id": "CLM-001",
      "outcome": "granted_in_part",
      "command": "...",
      "period": "...",
      "effects": [],
      "calculation_criteria": [],
      "source_analysis_id": "ANL-001"
    }
  ]
}
```

Cada pedido conhecido possui exatamente uma análise e um dispositivo. Resultados de mérito
exigem fatos, provas, avaliação das provas, normas aplicáveis e fundamentação. Resultados
processuais exigem fatos e normas; resultados inconclusivos exigem limitações explícitas. O
dispositivo herda o resultado analisado e se vincula por um identificador estável `ANL-*`.

---

## 8. Fluxo do primeiro grau

```text
0. Preparar e validar o perfil
   └─ case-context.json + manifesto do espaço de trabalho

1. Obter o processo
   ├─ validar a sessão
   ├─ descobrir tarefas e processos
   ├─ indexar documentos
   └─ baixar documentos autorizados

2. Extrair os autos processuais
   ├─ classificar documentos
   ├─ montar a linha do tempo processual
   └─ elaborar o relatório trabalhista

3. Montar as unidades de decisão
   ├─ matriz de pedidos
   ├─ mapeamento das defesas
   ├─ mapeamento das providências requeridas
   └─ matriz de provas

4. Encaminhar cada pedido
   ├─ pesquisa jurídica
   ├─ análise das provas
   ├─ revisão de cálculos
   └─ revisão processual

5. Executar trilhas condicionais
   ├─ pesquisa TST/STF/BNP
   ├─ pesquisa de precedentes e jurisprudência do TRT12
   ├─ revisão probatória especializada
   └─ revisão dos critérios de cálculo

6. Analisar cada pedido
   └─ claim-analysis.json

7. Redigir a sentença
   ├─ fundamentação por pedido
   ├─ matriz do dispositivo
   └─ componentes da minuta

8. Consolidar deterministicamente
   └─ <CNJ_NUMBER>-labor-judgment.md

9. Revisar e aplicar os controles
   ├─ cobertura dos pedidos
   ├─ congruência entre fundamentação e dispositivo
   ├─ fidelidade das citações às fontes
   ├─ estado e hierarquia dos precedentes
   ├─ coerência dos critérios de cálculo
   └─ controle global final
```

Cada etapa deve permitir retomada. Uma nova execução só pode reutilizar artefatos aprovados
na versão vigente do esquema, no controle de conteúdo, na conferência de atualização das
dependências e na impressão digital da fonte.

---

## 9. Plano dos agentes

| Agente | Capacidade individual | Estratégia de origem | Ação no MVP |
|---|---|---|---|
| `labor-document-classifier` | Classificar um documento indexado | Novo | Criar |
| `labor-procedural-timeline` | Extrair eventos processuais | Adaptar agente de linha do tempo existente | Incorporar |
| `labor-case-reporter` | Relatar pedidos, defesas, eventos e pendências | Adaptar agente de relatório existente | Incorporar |
| `labor-claim-mapper` | Enumerar pedidos e providências requeridas | Novo | Criar |
| `labor-evidence-mapper` | Relacionar provas a alegações controvertidas e pedidos | Novo | Criar |
| `labor-issue-router` | Encaminhar cada pedido às trilhas necessárias | Novo | Criar |
| `tst-precedent-researcher` | Pesquisar fontes autorizadas do TST | Novo | Criar |
| `trt12-precedent-researcher` | Pesquisar precedentes e jurisprudência do TRT12 | Novo | Criar |
| `labor-precedent-consolidator` | Hierarquizar e conciliar autoridades | Adaptar consolidador de pesquisa | Incorporar |
| `labor-claim-analyzer` | Analisar um pedido com provas e autoridades | Novo | Criar |
| `labor-judgment-drafter` | Redigir fundamentação e dispositivo a partir de análises aprovadas | Novo | Criar |
| `labor-congruence-reviewer` | Verificar cobertura entre pedidos, fundamentação e dispositivo | Novo | Criar |
| `labor-source-reviewer` | Verificar estado, hierarquia, texto e pertinência das fontes | Adaptar revisor de fontes | Incorporar |
| `labor-calculation-reviewer` | Revisar critérios, períodos e efeitos | Substituir revisor de cálculos federais | Criar |

As capacidades genéricas existentes de análise documental, testemunhal, pericial, digital,
de confissão e de reconhecimento só podem ser reaproveitadas depois de demonstrado que seus
exemplos e contratos não introduzem pressupostos da Justiça Federal.

---

## 10. Plano de habilidades e adaptadores

| Componente | Responsabilidade | Escopo |
|---|---|---|
| `tribunal-profile` | Carregar e validar perfis de tribunais | Núcleo |
| `pje-jt` | Fluxo do PJe-JT e contrato do adaptador | Justiça do Trabalho |
| `pje-jt-trt12-first-instance` | Endpoints observados e comportamento de sessão do TRT12 | Perfil TRT12 |
| `labor-claim-taxonomy` | Vocabulário de pedidos e providências | Justiça do Trabalho |
| `labor-precedent-hierarchy` | Âmbito vinculante, estado, distinção e superação | Justiça do Trabalho |
| `labor-evidence-review` | Orientações sobre provas trabalhistas | Justiça do Trabalho |
| `labor-calculation-criteria` | Revisão de critérios sem alegar liquidação independente | Justiça do Trabalho |
| `tst-jurisprudence` | Adaptador de pesquisa em fonte oficial do TST | Nacional |
| `trt12-jurisprudence` | Adaptador de pesquisa em fonte oficial do TRT12 | Perfil TRT12 |

Nenhum adaptador pode registrar cookies de sessão, material de MFA, cabeçalhos de
autorização, texto integral do processo ou identificadores pessoais não expurgados em
saídas de diagnóstico.

---

## 11. Política de autoridade na pesquisa

O consolidador deve preservar a seguinte hierarquia e registrar expressamente as exceções:

1. autoridade vinculante do STF aplicável à questão;
2. precedentes qualificados do TST e outras autoridades trabalhistas vinculantes em âmbito nacional;
3. súmulas, orientações e precedentes normativos vigentes do TST, conforme seu peso jurídico;
4. IRDR, IAC, teses regionais e outras autoridades regionais vinculantes do TRT12;
5. jurisprudência do TRT12, com identificação da câmara ou turma;
6. decisões de outros TRTs, identificadas apenas como persuasivas;
7. doutrina, somente se autorizada por uma pessoa para o fluxo específico, nunca inserida
   silenciosamente na minuta automatizada.

A saída da pesquisa deve registrar:

- fonte e URL oficial;
- estado atual, quando informado pela fonte;
- âmbito vinculante;
- questão jurídica e tese;
- trecho literal;
- data e hora da consulta;
- suspensão, superação, cancelamento ou conflito não resolvido que tenha sido identificado.

---

## 12. Controles determinísticos

| Controle | Condições de bloqueio | Evidência de saída |
|---|---|---|
| Perfil | Configuração inválida ou incompleta do tribunal | Relatório de validação do perfil |
| Entrada | Número CNJ do TRT12 inválido, autorização ausente ou fonte ilegível | Relatório de entrada |
| Índice de documentos | IDs ausentes, duplicatas ou lacunas de download sem explicação | Relatório do índice |
| Cobertura dos pedidos | Pedido formulado ausente da matriz | Relatório de conciliação dos pedidos |
| Cobertura das defesas | Pedido contestado sem defesa mapeada nem estado explícito de ausência de defesa | Relatório de conciliação das defesas |
| Custódia das provas | Alegação probatória sem localizador da fonte | Relatório de provas |
| Encaminhamento | Pedido sem encaminhamento válido e justificado | Relatório de encaminhamento |
| Pesquisa | Autoridade citada fora do corpus autorizado ou com estado não resolvido | Relatório de pesquisa |
| Análise | Pedido sem fatos, norma, fundamentação, resultado ou campo de limitação | Relatório de análise |
| Congruência do dispositivo | Pedido sem dispositivo ou dispositivo sem pedido correspondente | Relatório de congruência |
| Citações | Citação externa divergente do corpus autorizado | Relatório de citações |
| Critérios de cálculo | Período, efeito ou critério incoerente ou sem suporte | Relatório de cálculos |
| Final | Qualquer controle bloqueante falhou ou algum artefato está desatualizado | Relatório global |

Controles críticos não podem ser rebaixados a avisos. Um pedido pode terminar em abstenção
explícita ou solicitação de decisão humana, mas não pode desaparecer silenciosamente.

---

## 13. Segurança e privacidade

Antes de ingerir um processo real, o projeto deve implementar e verificar:

- regras para ignorar `.env`, sessões, HAR, cookies, autorizações e dados processuais;
- arquivos HAR sanitizados para testes;
- expurgo nos registros, com testes para todos os campos de credenciais;
- acesso a ferramentas com privilégio mínimo para cada agente;
- ausência de ferramentas de escrita externa ou protocolo no fluxo do MVP;
- política para processos sigilosos aprovada pela pessoa responsável;
- regras de retenção e exclusão dos espaços locais de trabalho dos processos;
- confirmação explícita de que o modelo e a infraestrutura escolhidos atendem aos requisitos
  do tribunal para tratamento dos dados.

---

## 14. Estratégia de validação

### 14.1 Camadas de testes

1. **Testes de esquema:** exemplos válidos e inválidos para cada contrato estável.
2. **Testes unitários:** controles, normalização, consolidação, impressões digitais e expurgo.
3. **Testes de contrato dos adaptadores:** respostas gravadas e sanitizadas do PJe e da pesquisa.
4. **Testes de integração:** fluxo completo com dados sintéticos e sanitizados.
5. **Revisão histórica cega:** processos encerrados do primeiro grau do TRT12 cujos
   resultados ficam ocultos durante a geração e só são examinados na avaliação.
6. **Suíte de regressão:** todos os defeitos confirmados tornam-se casos de teste permanentes.

### 14.2 Metas provisórias de aceite

As metas são provisórias até que a primeira amostra de calibração estabeleça uma linha de base.

| Indicador | Meta do MVP | Limite de segurança |
|---|---:|---|
| Sensibilidade na extração de pedidos | pelo menos 95% | 100% dos pedidos na amostra de aceite antes do piloto |
| Cobertura entre pedidos e dispositivo | 100% | Qualquer omissão é crítica |
| Fidelidade das citações literais | 100% | Qualquer citação sem suporte é crítica |
| Dispositivos sem pedido correspondente | 0% | Qualquer ocorrência é crítica |
| Falhas silenciosas de adaptadores | 0% | Indisponibilidade explícita é aceitável |
| Êxito do ensaio autorizado no PJe | pelo menos 95% | Nenhum vazamento de credenciais |
| Defeitos críticos na revisão cega final | 0 | Bloqueia a prontidão para o piloto |

O protocolo da amostra histórica deve definir seleção de processos, categorias de pedidos,
ritos, instruções aos revisores e gravidade dos defeitos antes de observar os resultados.

---

## 15. Organização prevista do repositório

```text
.
├── runtime/
│   ├── contracts/
│   │   ├── catalog.json
│   │   ├── VERSIONING.md
│   │   └── schemas/
│   │       └── *.v1.schema.json
│   ├── domain/
│   │   ├── labor-document-classification.json
│   │   └── README.md
│   ├── profiles/
│   │   ├── schema.json
│   │   ├── registry.json
│   │   └── trt12.json
│   └── providers/
│       ├── har-sanitization-contract.json
│       ├── har-map-review-contract.json
│       ├── interfaces.json
│       ├── pje-session-contract.json
│       ├── pje-task-discovery-contract.json
│       └── README.md
├── scaffold/
│   ├── commands/
│   │   ├── pipeline-labor-judgment.md
│   │   └── pipeline-labor-vote.md          # futuro, desabilitado
│   ├── agents/
│   │   ├── labor/
│   │   ├── research/
│   │   ├── drafting/
│   │   └── review/
│   ├── skills/
│   │   ├── tribunal-profile/
│   │   ├── pje-jt/
│   │   ├── labor-claim-taxonomy/
│   │   ├── labor-precedent-hierarchy/
│   │   └── labor-calculation-criteria/
│   └── adapters/
│       ├── pje-jt/
│       │   └── trt12-first-instance/
│       └── research/
│           ├── tst/
│           └── trt12/
├── scripts/
│   ├── validate_tribunal_profile.py
│   ├── build_claim_matrix.py
│   ├── build_claim_decisions.py
│   ├── build_evidence_matrix.py
│   ├── build_issue_routes.py
│   ├── build_labor_report.py
│   ├── classify_labor_documents.py
│   ├── provider_interfaces.py
│   ├── pje_session_adapter.py
│   ├── pje_task_discovery.py
│   ├── sanitize_pje_har.py
│   ├── validate_pje_har_map.py
│   ├── validate_claims.py
│   ├── validate_congruence.py
│   └── verify_labor_judgment.py
└── tests/
    ├── contracts/
    ├── gates/
    ├── adapters/
    ├── integration/
    └── fixtures/
        ├── synthetic/
        └── sanitized/
```

A organização física exata pode se adaptar às convenções existentes do projeto durante a
implementação. A separação lógica entre núcleo, domínio trabalhista e perfil do tribunal é
obrigatória.

---

## 16. Contrato de extensão para o segundo grau

A implementação do primeiro grau não deve incluir comportamento de segundo grau, mas não pode
impedir sua inclusão futura. O futuro fluxo do segundo grau acrescentará:

- admissibilidade recursal;
- matriz dos capítulos impugnados;
- limites da devolução recursal;
- razões e contrarrazões;
- manutenção, reforma ou anulação por capítulo;
- metadados de turma regional e divergência;
- revisão de prequestionamento, quando aplicável;
- contratos de saída para voto e acórdão.

O fluxo de segundo grau reaproveitará obtenção do processo, classificação de documentos,
custódia das provas e dos precedentes, revisão das fontes e mecanismos centrais de execução.

---

## 17. Contrato de extensão para outros TRTs

Um segundo TRT só será considerado suportado quando tiver:

- perfil aprovado;
- adaptador PJe do primeiro grau verificado ou adaptador compartilhado comprovado;
- adaptador de pesquisa regional verificado;
- política local de precedentes;
- dados de teste sanitizados;
- resultados de regressão de ponta a ponta;
- dossiê de validação histórica aprovado.

O primeiro TRT adicional será o teste de portabilidade. Até sua aprovação, o projeto é
**extensível a partir do TRT12**, não **compatível com múltiplos TRTs**.

---

## 18. Decisões arquiteturais

| ID | Decisão | Justificativa |
|---|---|---|
| ADR-001 | O primeiro grau do TRT12 é o primeiro alvo executável | Mantém a validação delimitada |
| ADR-002 | Primeiro e segundo graus usam orquestradores separados | Seus fluxos jurídicos diferem substancialmente |
| ADR-003 | O pedido é a unidade primária de decisão | Evita pedidos omitidos ou confundidos |
| ADR-004 | Diferenças entre tribunais ficam nos perfis e adaptadores | Preserva agentes de domínio reutilizáveis |
| ADR-005 | Conhecer o PJe-Calc não equivale a liquidar de forma independente | Evita exagerar a correção dos cálculos |
| ADR-006 | Progresso só é contabilizado com evidência aceita | Evita indicadores falsos de conclusão |
| ADR-007 | Um segundo TRT é necessário para comprovar portabilidade | Evita abstração especulativa |
| ADR-008 | Contratos de provedores são definidos por capacidade e independentes do tribunal | Mantém endpoints e particularidades fora do núcleo compartilhado |
| ADR-009 | HARs brutos e sessões permanecem locais; apenas mapas sanitizados e revisados podem servir de evidência | Impede credenciais e conteúdo processual no controle de versão |
| ADR-010 | A classificação da sessão é separada da obtenção de credenciais e bloqueia ambiguidades | Mantém o núcleo sem segredos e evita presumir autenticação |
| ADR-011 | A descoberta usa páginas normalizadas e limitadas; fila vazia é resultado completo | Evita perda silenciosa na paginação sem embutir dados do provedor no núcleo |
| ADR-012 | A classificação documental trabalhista é versionada, determinística e preserva estados desconhecidos/conflitantes | Permite auditoria sem apresentar hipótese não calibrada como fato |
| ADR-013 | O relatório trabalhista é estruturado, vinculado às fontes e preserva lacunas | Evita que narrativas se tornem referência sem rastreabilidade |
| ADR-014 | Posições sobre pedidos e defesas mantêm fontes independentes; divergências da taxonomia são explícitas | Evita fundir silenciosamente defesas de múltiplos reclamados ou pedidos novos |
| ADR-015 | Provas são ligadas aos pedidos e às fontes, preservam limitações e registram contradições | Evita que alegações sem suporte ou provas conflitantes desapareçam na síntese |
| ADR-016 | Cada pedido recebe um encaminhamento explicável ou abstenção explícita | Evita perda de pedidos entre extração estruturada e análise jurídica |
| ADR-017 | Análises e dispositivos formam uma cadeia individual por pedido, com IDs estáveis | Evita divergência entre fundamentação, comando e montagem determinística |

---

## 19. Decisões em aberto antes da implementação

Elas não impedem o aceite do blueprint, mas bloqueiam os pacotes de trabalho indicados:

1. contexto de acesso autorizado ao PJe-JT do TRT12 e captura HAR sanitizada;
2. nomes exatos das tarefas e tipos de documentos do primeiro grau usados pela unidade alvo;
3. política aprovada para tratamento de dados pessoais e processos sigilosos;
4. amostra histórica mínima e disponibilidade de revisores;
5. escolha entre interoperabilidade com PJe-Calc por arquivo, comparação manual ou adiamento;
6. estilo preferido de sentença e existência de modelo inicial aprovado.

---

## 20. Registro de aceite do blueprint

O usuário aprovou este blueprint em 2026-09-21 e confirmou:

- primeiro grau do TRT12 como primeiro alvo executável;
- segundo grau como fluxo futuro separado;
- suporte a outros TRTs por perfis e adaptadores, após comprovar a portabilidade;
- rastreabilidade obrigatória de cada pedido;
- progresso medido pelo roadmap ponderado por evidências;
- nenhuma automação de protocolo, assinatura ou publicação no MVP.

O item `ARC-01` do roadmap recebe, portanto, seus três pontos previstos. O projeto segue
para os demais critérios de aceite da fundação e dos contratos.

---

## 21. Referências oficiais do domínio

- Numeração única do CNJ e dígito do ramo da Justiça do Trabalho:
  <https://www.cnj.jus.br/programas-e-acoes/numeracao-unica/perguntas-frequentes/>
- Banco Nacional de Precedentes do CNJ:
  <https://www.cnj.jus.br/tecnologia-da-informacao-e-comunicacao/justica-4-0/banco-nacional-de-precedentes-bnp/>
- Carta de Serviços do TRT12, inclusive acessos distintos ao PJe do primeiro e segundo graus
  e abrangência da consulta jurisprudencial:
  <https://portal.trt12.jus.br/sites/default/files/2025-08/Carta%20de%20Servi%C3%A7os%20TRT12%20%281%29.pdf>
- Consulta à jurisprudência do TRT12:
  <https://portal.trt12.jus.br/consulta-jurisprudencia>
- Uniformização de precedentes e jurisprudência do TRT12:
  <https://portal.trt12.jus.br/uniformizacao-jurisprudencia>
- Informativo de precedentes do TRT12:
  <https://portal.trt12.jus.br/informativo-de-precedentes-2024>
- Jurisprudência do TST:
  <https://www.tst.jus.br/jurisprudencia>
- Índice temático de precedentes qualificados do TST:
  <https://www.tst.jus.br/indice-tematico-precedentes-qualificados-tst>
- Jurisprudência do STF:
  <https://portal.stf.jus.br/jurisprudencia/>
