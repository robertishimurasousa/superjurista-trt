# SuperJurista TRT

Este fork adapta os fluxos, agentes e controles do SuperJurista original para
processos trabalhistas do primeiro grau do TRT12. Não é uma implementação do
zero. O segundo grau do TRT12 e outros TRTs estão previstos como extensões,
mas ainda não foram validados. O uso com autos reais exige autorização
específica, controles de dados e revisão jurídica humana; ensaios sintéticos
e testes técnicos não equivalem a uma decisão judicial validada.

O [plano arquitetural](spec/blueprints/superjurista-trt12-first-instance-BLUEPRINT.md)
descreve o reaproveitamento do fork. O [roteiro de desenvolvimento](spec/roadmaps/superjurista-trt12-ROADMAP.md)
registra critérios de aceite, evidências, bloqueios e avanço ponderado. Para
instalação e operação supervisionada do fluxo TRT12, siga o
[manual do operador](spec/operations/trt12-first-instance-operator-runbook.md).

O repositório também preserva o plugin de meta-ferramentas para Claude Code,
capaz de criar agentes, orquestradores, habilidades e projetos derivados. As
instruções de instalação desse plugin, abaixo, descrevem a capacidade herdada;
instalar o plugin original pelo marketplace **não instala nem valida** a
adaptação TRT12 deste fork.

## Idioma do projeto

Documentação interna, instruções dos agentes, modelos, formulários, relatórios e
documentos gerados para pessoas devem usar português brasileiro com acentuação.
Nomes de comandos, arquivos, chaves de contratos e citações literais dos autos
permanecem inalterados. A regra está em [`AGENTS.md`](AGENTS.md) para os trabalhos
no repositório e em [`scaffold/project-claude.md`](scaffold/project-claude.md) para
instalações no Claude Code. Os documentos ativos herdados em inglês estão sendo
localizados em etapas; esta regra não indica que a tradução retroativa já terminou.

## Instalação do plugin herdado

### Opção 1: Dentro de uma sessão do Claude Code

Os comandos abaixo instalam o plugin original e seu scaffold no projeto atual.
Para trabalhar neste fork, use o manual do operador indicado acima.

```
/plugin marketplace add georgemarmelstein/superjurista-marketplace
/plugin install superjurista-dev@georgemarmelstein-superjurista-marketplace
/instalar-superjurista
```

**Passo a passo:**

1. **Adicionar o marketplace** -- registra o repositório de plugins do SuperJurista:
   ```
   /plugin marketplace add georgemarmelstein/superjurista-marketplace
   ```

2. **Instalar o plugin** -- baixa as meta-ferramentas e o scaffold:
   ```
   /plugin install superjurista-dev@georgemarmelstein-superjurista-marketplace
   ```

3. **Instalar o sistema no projeto** -- copia agentes, pipelines, habilidades e MCPs para `.claude/`:
   ```
   /instalar-superjurista
   ```

### Opção 2: Via interface interativa

Digite `/plugin` para abrir o gerenciador visual com abas (Discover, Installed, Marketplaces, Errors). Navegue com Tab/Shift+Tab.

### Opção 3: Desenvolvimento local do plugin original

```bash
git clone https://github.com/georgemarmelstein/superjurista-dev.git
claude --plugin-dir ./superjurista-dev
```

Depois, dentro da sessão: `/instalar-superjurista`. Esse clone aponta para o
projeto original, não para este fork TRT12.

## Gerenciamento do plugin

| Ação | Comando |
|------|---------|
| Abrir gerenciador interativo | `/plugin` |
| Adicionar marketplace | `/plugin marketplace add owner/repo` |
| Instalar plugin | `/plugin install plugin@marketplace` |
| Listar instalados | `/plugin` > aba Installed |
| Desinstalar | `/plugin uninstall superjurista-dev@georgemarmelstein-superjurista-marketplace` |
| Desativar (sem remover) | `/plugin disable superjurista-dev@georgemarmelstein-superjurista-marketplace` |
| Reativar | `/plugin enable superjurista-dev@georgemarmelstein-superjurista-marketplace` |
| Recarregar após instalar | `/reload-plugins` |

### Escopo da instalação

Ao instalar, você pode escolher o escopo:

- **user** -- funciona em todos os seus projetos (padrão)
- **project** -- salva em `.claude/settings.json` do repositório (todos que clonarem terão o plugin)
- **local** -- só você, só neste repositório

### Pré-requisito

Para o plugin original, a versão mínima documentada do Claude Code é **1.0.33+**.
Se `/plugin` não aparecer:

```bash
npm update -g @anthropic-ai/claude-code
```

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/instalar-superjurista` | Instala o sistema SuperJurista completo no projeto atual |
| `/criar-agente` | Cria agentes modulares seguindo as SPECs v2.0 |
| `/criar-orquestrador` | Cria orquestradores (commands) com injecao de contexto |
| `/criar-skill` | Cria skills com TDD e CSO (Claude Search Optimization) |
| `/criar-team` | Cria Agent Teams (paralelo ou debate) |
| `/planejar-sistema` | Gera blueprint arquitetural antes de criar artefatos |

## Habilidades

- **criar-sistema**: Motor de geração de sistemas de agentes inteiros (1 orquestrador + N agentes + M habilidades) a partir de uma descrição de intenção -- plano arquitetural como contrato, geração em ondas por 5 agentes especializados (geradores + validadores adversariais), preparação e commit atômico. Opções: `--revisar`, `--target=PATH`.
- **criar-skill**: Fluxo TDD para criação de habilidades -- verifica se a habilidade ensina o comportamento correto ao Claude, com testes de conformidade e otimização para busca interna.
- **criar-mcp-precedente**: Guia para criar servidores MCP de jurisprudência — tribunais brasileiros e cortes internacionais (comprovado em CJF, TCU, TJSC/eProc e HUDOC/CEDH). Descoberta de endpoints e sintaxe booleana, modelo com busca compartilhada, registro via `.mcp.json` e roteamento em 3 rotas: MCP de extração, mcp-builder (REST documentada) ou habilidade via Chrome MCP (portais com CAPTCHA por requisição).
- **criar-pje-download**: Cria habilidades de download do PJe para qualquer tribunal via engenharia reversa de arquivos HAR -- identifica endpoints, cookies, cabeçalhos e gera scripts Python parametrizados.

## O que o /instalar-superjurista cria

No plugin original, o comando `/instalar-superjurista` gera um sistema judicial
no projeto atual. O inventário abaixo descreve esse scaffold herdado, não
capacidade trabalhista aceita para o TRT12:

- **16 pipelines e comandos** para processamento judicial (sentença, embargos, pesquisa, revisão, etc.)
- **~52 agentes especializados** em 7 categorias (extração, análise, pesquisa, redação, revisão, lista-trf, tribunal)
- **6 habilidades de domínio** (download PJe, conversão PDF, análise probatória, captura de sessão, etc.)
- **5 servidores MCP** (BNP/CNJ, CJF Unificada, TCU, TJSC eProc, TNU eProc), registrados automaticamente no `.mcp.json` do projeto
- **Estrutura de dados pronta** (`data/sentenca/`, `data/decisao/`)
- **CLAUDE.md e README.md** configurados para o projeto

### Estrutura gerada

```
projeto/
├── .claude/
│   ├── commands/           # 16 pipelines e comandos
│   ├── agents/
│   │   ├── analise/        # Marmelstein, Haack, Pearl, embargos, probatória
│   │   ├── extracao/       # Linha do tempo, relator, conversor
│   │   ├── lista-trf/      # 9 agentes para listas de julgamento
│   │   ├── pesquisa/       # BNP, CJF, JULIA, consolidador
│   │   ├── redacao/        # Redator de minutas
│   │   ├── revisao/        # Verificadores (cálculos, honorários, fontes)
│   │   └── tribunal/       # Acusador, defensor, juiz mediador
│   ├── skills/
│   │   ├── pje-download/   # API REST do PJE (10 scripts Python)
│   │   ├── converter-pdf/  # Conversão PDF para TXT com OCR híbrido
│   │   ├── analise-probatoria/  # Listas de verificação por tipo de prova
│   │   ├── capturar-sessao-pje/ # Captura de sessão via Chrome MCP
│   │   ├── analisador-erro-medico/ # Análise de erro médico
│   │   └── fork-terminal/  # Execução paralela em terminais
│   └── mcp-servers/
│       ├── bnp-api/        # Banco Nacional de Precedentes (STF/STJ)
│       ├── cjf-jurisprudencia/ # Portal unificado CJF
│       ├── tcu-jurisprudencia/ # Jurisprudência TCU (3 bases)
│       ├── tjsc-eproc/     # Jurisprudência TJSC
│       └── tnu-eproc/      # TNU viva com inteiro teor
├── .mcp.json               # Registro dos 5 MCPs (gerado na instalação)
├── scripts/                # Controles determinísticos v3.0 (verificar_pipeline, verificar_sentenca, merge_sentenca)
├── data/
│   ├── sentenca/           # Processos para sentença
│   └── decisao/            # Processos para decisão
├── CLAUDE.md               # Configuração do projeto
└── README.md               # Documentação do projeto
```

## Arquitetura herdada

O sistema original usa o padrão "Orquestrador Cego" com injeção de contexto.
Os orquestradores delegam tarefas a agentes com contexto isolado; cada agente
lê suas instruções, grava o documento em disco e devolve uma linha de estado.
Controles determinísticos verificam as transferências entre etapas, e o
pipeline permite retomada. Neste fork, o [contrato de execução](runtime/README.md)
separa as regras compartilhadas dos adaptadores de Claude Code e Codex.
Modelos e referências herdados permanecem em `spec/`.

## Dependências

Os scripts centrais exigem Python 3.9 ou superior. Os servidores MCP locais
exigem Python 3.10 ou superior pela versão suportada do SDK (`mcp>=1.28,<2`).
Crie o ambiente local compartilhado com Python 3.10 ou superior:

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

No macOS, o OCR também exige Tesseract com dados do idioma português e Poppler:

```bash
brew install tesseract tesseract-lang poppler
python3 scripts/rehearse_target_host.py --root .
```

O ensaio importa os servidores MCP preservados e executa o conversor PDF
herdado com Poppler e OCR em português. O contrato de Python legível por
máquina está em `runtime/python-contract.json`.

## Controle de qualidade

O desenvolvimento local usa este ponto de entrada determinístico:

```bash
python3 scripts/quality_gate.py --root .
```

O comando valida os contratos de Python, a formatação e a sintaxe do código,
a proteção de credenciais e dados processuais, o perfil do TRT12, esquemas e
amostras de artefatos jurídicos, contratos JSON, o inventário de reuso e a
suíte de testes. O GitHub Actions está configurado para execução **manual**;
pushes e solicitações de alteração não o disparam automaticamente neste momento.

## Proteção de dados

O repositório rejeita arquivos de ambiente preparados para commit, capturas
autenticadas do navegador, sessões do PJe, depósitos de cookies e cabeçalhos,
logs e diretórios locais de autos. O verificador não abre arquivos locais
devidamente ignorados.

```bash
python3 scripts/check_data_hygiene.py \
  --root . \
  --contract runtime/data-hygiene-contract.json
```

Os achados mostram apenas caminho, número da linha e identificador da regra;
valores de segredos não são impressos. Amostras HAR sanitizadas só podem ficar
em `tests/fixtures/sanitized/` e devem respeitar o limite de tamanho do contrato.

## Licença

[MIT](LICENSE)
