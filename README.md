# superjurista-dev

Plugin de meta-ferramentas para criar e customizar sistemas agenticos judiciais com Claude Code. Inclui ferramentas para criar agentes, orquestradores, skills, teams e um scaffold completo do sistema SuperJurista -- um sistema de inteligencia aumentada para processamento de processos judiciais, construido com arquitetura de pipelines deterministicos.

## Idioma do projeto

Documentação interna, instruções dos agentes, modelos, formulários, relatórios e
documentos gerados para pessoas devem usar português brasileiro com acentuação.
Nomes de comandos, arquivos, chaves de contratos e citações literais dos autos
permanecem inalterados. A regra está em [`AGENTS.md`](AGENTS.md) para os trabalhos
no repositório e em [`scaffold/project-claude.md`](scaffold/project-claude.md) para
instalações no Claude Code. Os documentos ativos herdados em inglês estão sendo
localizados em etapas; esta regra não indica que a tradução retroativa já terminou.

## Instalacao

### Opcao 1: Dentro de uma sessao do Claude Code (recomendado)

Tres comandos e o sistema inteiro esta funcionando:

```
/plugin marketplace add georgemarmelstein/superjurista-marketplace
/plugin install superjurista-dev@georgemarmelstein-superjurista-marketplace
/instalar-superjurista
```

**Passo a passo:**

1. **Adicionar o marketplace** -- registra o repositorio de plugins do SuperJurista:
   ```
   /plugin marketplace add georgemarmelstein/superjurista-marketplace
   ```

2. **Instalar o plugin** -- baixa as meta-ferramentas e o scaffold:
   ```
   /plugin install superjurista-dev@georgemarmelstein-superjurista-marketplace
   ```

3. **Instalar o sistema no projeto** -- copia agentes, pipelines, skills e MCPs para `.claude/`:
   ```
   /instalar-superjurista
   ```

### Opcao 2: Via interface interativa

Digite `/plugin` para abrir o gerenciador visual com abas (Discover, Installed, Marketplaces, Errors). Navegue com Tab/Shift+Tab.

### Opcao 3: Desenvolvimento local

```bash
git clone https://github.com/georgemarmelstein/superjurista-dev.git
claude --plugin-dir ./superjurista-dev
```

Depois, dentro da sessao: `/instalar-superjurista`

## Gerenciamento do plugin

| Acao | Comando |
|------|---------|
| Abrir gerenciador interativo | `/plugin` |
| Adicionar marketplace | `/plugin marketplace add owner/repo` |
| Instalar plugin | `/plugin install plugin@marketplace` |
| Listar instalados | `/plugin` > aba Installed |
| Desinstalar | `/plugin uninstall superjurista-dev@georgemarmelstein-superjurista-marketplace` |
| Desativar (sem remover) | `/plugin disable superjurista-dev@georgemarmelstein-superjurista-marketplace` |
| Reativar | `/plugin enable superjurista-dev@georgemarmelstein-superjurista-marketplace` |
| Recarregar apos instalar | `/reload-plugins` |

### Escopo da instalacao

Ao instalar, voce pode escolher o escopo:

- **user** -- funciona em todos os seus projetos (padrao)
- **project** -- salva em `.claude/settings.json` do repo (todos que clonarem terao o plugin)
- **local** -- so voce, so neste repositorio

### Pre-requisito

Versao minima do Claude Code: **1.0.33+**. Se `/plugin` nao aparecer:

```bash
npm update -g @anthropic-ai/claude-code
```

## Comandos

| Comando | Descricao |
|---------|-----------|
| `/instalar-superjurista` | Instala o sistema SuperJurista completo no projeto atual |
| `/criar-agente` | Cria agentes modulares seguindo as SPECs v2.0 |
| `/criar-orquestrador` | Cria orquestradores (commands) com injecao de contexto |
| `/criar-skill` | Cria skills com TDD e CSO (Claude Search Optimization) |
| `/criar-team` | Cria Agent Teams (paralelo ou debate) |
| `/planejar-sistema` | Gera blueprint arquitetural antes de criar artefatos |

## Skills

- **criar-sistema**: Motor de geracao de sistemas agenticos inteiros (1 orquestrador + N agentes + M skills) a partir de uma descricao de intencao -- blueprint como contrato, geracao em ondas por 5 agentes especializados (geradores + validadores adversariais), staging e commit atomico. Flags: `--revisar`, `--target=PATH`.
- **criar-skill**: Workflow TDD para criacao de skills -- garante que a skill ensina o comportamento correto ao Claude, com testes de conformidade e otimizacao para busca interna.
- **criar-mcp-precedente**: Guia para criar servidores MCP de jurisprudencia — tribunais brasileiros e cortes internacionais (comprovado em CJF, TCU, TJSC/eProc e HUDOC/CEDH). Descoberta de endpoints e sintaxe booleana, template com busca compartilhada, registro via `.mcp.json` e roteamento em 3 rotas: MCP de scraping, mcp-builder (REST documentada) ou skill via Chrome MCP (portais com CAPTCHA por requisicao).
- **criar-pje-download**: Cria skills de download do PJE para qualquer tribunal via engenharia reversa de arquivos HAR -- identifica endpoints, cookies, headers e gera scripts Python parametrizados.

## O que o /instalar-superjurista cria

O comando `/instalar-superjurista` gera um sistema judicial completo no projeto atual:

- **16 pipelines e comandos** para processamento judicial (sentenca, embargos, pesquisa, revisao, etc.)
- **~52 agentes especializados** em 7 categorias (extracao, analise, pesquisa, redacao, revisao, lista-trf, tribunal)
- **6 skills de dominio** (download PJE, conversao PDF, analise probatoria, captura de sessao, etc.)
- **5 servidores MCP** (BNP/CNJ, CJF Unificada, TCU, TJSC eProc, TNU eProc), registrados automaticamente no `.mcp.json` do projeto
- **Estrutura de dados pronta** (`data/sentenca/`, `data/decisao/`)
- **CLAUDE.md e README.md** configurados para o projeto

### Estrutura gerada

```
projeto/
├── .claude/
│   ├── commands/           # 16 pipelines e comandos
│   ├── agents/
│   │   ├── analise/        # Marmelstein, Haack, Pearl, embargos, probatoria
│   │   ├── extracao/       # Linha do tempo, relator, conversor
│   │   ├── lista-trf/      # 9 agentes para listas de julgamento
│   │   ├── pesquisa/       # BNP, CJF, JULIA, consolidador
│   │   ├── redacao/        # Redator de minutas
│   │   ├── revisao/        # Verificadores (calculos, honorarios, fontes)
│   │   └── tribunal/       # Acusador, defensor, juiz mediador
│   ├── skills/
│   │   ├── pje-download/   # API REST do PJE (10 scripts Python)
│   │   ├── converter-pdf/  # Conversao PDF para TXT com OCR hibrido
│   │   ├── analise-probatoria/  # Checklists por tipo de prova
│   │   ├── capturar-sessao-pje/ # Captura sessao via Chrome MCP
│   │   ├── analisador-erro-medico/ # Analise de erro medico
│   │   └── fork-terminal/  # Execucao paralela em terminais
│   └── mcp-servers/
│       ├── bnp-api/        # Banco Nacional de Precedentes (STF/STJ)
│       ├── cjf-jurisprudencia/ # Portal unificado CJF
│       ├── tcu-jurisprudencia/ # Jurisprudencia TCU (3 bases)
│       ├── tjsc-eproc/     # Jurisprudencia TJSC
│       └── tnu-eproc/      # TNU viva com inteiro teor
├── .mcp.json               # Registro dos 5 MCPs (gerado na instalacao)
├── scripts/                # Gates deterministicos v3.0 (verificar_pipeline, verificar_sentenca, merge_sentenca)
├── data/
│   ├── sentenca/           # Processos para sentenca
│   └── decisao/            # Processos para decisao
├── CLAUDE.md               # Configuracao do projeto
└── README.md               # Documentacao do projeto
```

## Framework

O sistema baseia-se no framework v3.0 de orquestracao agentica com padrao "Orquestrador Cego" e injecao de contexto. Neste padrao, commands (orquestradores) delegam tarefas via Task tool para subagentes que possuem contexto isolado -- cada agente le seu proprio prompt, GRAVA o documento em disco e responde 1 linha de status. A validacao entre etapas e deterministica, por gate de script (`scripts/verificar_<sistema>.py`), e os pipelines sao retomaveis: a varredura inicial lista as etapas PENDENTES e etapa ja valida nao roda de novo. Templates e referencias completas estao disponiveis em `spec/`.

## Dependencies

The core scripts require Python 3.9 or newer. Local MCP servers require Python
3.10 or newer because the supported MCP SDK line is `mcp>=1.28,<2`. Use a
Python 3.10+ interpreter when creating the shared local environment:

```bash
/path/to/python3.12 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements/runtime.txt
for requirements_file in scaffold/mcp-servers/*/requirements.txt; do
  python3 -m pip install -r "$requirements_file"
done
python3 scripts/check_python_contract.py --root . \
  --contract runtime/python-contract.json --mode core
python3 scripts/check_python_contract.py --root . \
  --contract runtime/python-contract.json --mode mcp
```

On macOS, OCR also requires Tesseract with Portuguese language data and Poppler:

```bash
brew install tesseract tesseract-lang poppler
python3 scripts/rehearse_target_host.py --root .
```

The rehearsal imports every preserved MCP server and runs the preserved PDF converter through
Poppler and Portuguese OCR. The canonical machine-readable Python contract is
`runtime/python-contract.json`.

## Quality gate

Local development and CI use the same deterministic entry point:

```bash
python3 scripts/quality_gate.py --root .
```

It validates the Python contracts, source formatting, executable Python syntax,
credential and case-data hygiene, the TRT12 tribunal profile, legal artifact schemas and
fixtures, JSON contracts, the generated reuse ledger, and the complete unit-test suite.
GitHub Actions runs this command on the
supported Python 3.9 and Python 3.10 boundaries.

## Data hygiene

The repository rejects commit-ready environment files, authenticated browser
captures, PJe sessions, cookie/header stores, logs, and local case-data
directories. Properly ignored local files are not opened by the checker.

```bash
python3 scripts/check_data_hygiene.py \
  --root . \
  --contract runtime/data-hygiene-contract.json
```

Findings report only the path, line number, and rule identifier; matched secret
values are never printed. Sanitized HAR fixtures may be stored only under
`tests/fixtures/sanitized/` and must remain below the contract size limit.

## Licenca

[MIT](LICENSE)
