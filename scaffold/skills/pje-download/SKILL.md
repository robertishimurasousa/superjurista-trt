---
name: pje-download
description: Baixa processos do PJE via API REST. Use com /baixar-pje ou /baixar-converter.
context: fork
agent: general-purpose
allowed-tools: Bash, Read, Write
---

# PJE Download

> **Legacy boundary:** the scripts below implement the original TRF5 workflow and are retained
> as reuse evidence. They are not the TRT12 adapter. TRT12 task and process listing must bind
> reviewed provider evidence to `scripts/pje_task_discovery.py`; do not reuse TRF5 endpoints,
> task names, pagination behavior, or payload fields as TRT12 facts.

REGRA ABSOLUTA: Execute os scripts existentes. NAO crie codigo novo.

## Scripts Disponiveis

| Script | Comando |
|--------|---------|
| Extrair cookies HAR | `python3 .claude/skills/pje-download/scripts/extrair_cookies_har.py` |
| Sanitizar mapa HAR | `python3 scripts/sanitize_pje_har.py` |
| Validar mapa HAR | `python3 scripts/validate_pje_har_map.py` |
| Listar processos | `python3 .claude/skills/pje-download/scripts/listar_processos.py` |
| Baixar PDFs completos | `python3 .claude/skills/pje-download/scripts/baixar_pdfs.py` |
| Baixar por tipo | `python3 .claude/skills/pje-download/scripts/baixar_por_tipo.py` |
| Listar documentos | `python3 .claude/skills/pje-download/scripts/listar_documentos.py` |
| Buscar por numero | `python3 .claude/skills/pje-download/scripts/buscar_processo_por_numero.py` |
| Extrair indice | `python3 .claude/skills/pje-download/scripts/extrair_indice_completo.py` |
| Baixar por ID | `python3 .claude/skills/pje-download/scripts/baixar_por_id.py` |

## Comandos Prontos

### Extrair cookies de HAR (fallback)
```bash
python3 .claude/skills/pje-download/scripts/extrair_cookies_har.py \
  --har ~/Downloads/pje_sessao.har \
  --output pje_session.json
```

### Create a reviewable HAR evidence map

Keep the raw authorized HAR outside the repository. The command below removes values and
bodies while preserving the endpoint, capability, and failure-state structure needed by the
TRT adapter work:

```bash
python3 scripts/sanitize_pje_har.py \
  --input ~/Downloads/pje_authorized.har \
  --output tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1 \
  --authorized-capture
```

Review the generated JSON before committing it. Never commit the raw HAR or
`pje_session.json`.

```bash
python3 scripts/validate_pje_har_map.py \
  --map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1
```

Resolve every reported gap before requesting human review.

### Listar processos de uma fila
```bash
python3 .claude/skills/pje-download/scripts/listar_processos.py \
  --cookies pje_session.json \
  --modo sentenca \
  --limite 5 \
  --output processos.json
```

### Baixar PDFs completos
```bash
python3 .claude/skills/pje-download/scripts/baixar_pdfs.py \
  --cookies pje_session.json \
  --processos processos.json \
  --output data/sentenca \
  --delay 2
```

### Download seletivo (processos grandes)
```bash
python3 .claude/skills/pje-download/scripts/baixar_por_tipo.py \
  --cookies pje_session.json \
  --id-processo ID_AQUI \
  --relevantes \
  --output-dir data/sentenca/NUMERO/tipos/
```

---

## Navegacao Avancada

O script `listar_processos.py` suporta filtros avancados. Para ver todos:

```bash
python3 .claude/skills/pje-download/scripts/listar_processos.py --help
```

### Filtros Disponiveis

| Filtro | Descricao | Exemplo |
|--------|-----------|---------|
| `--tags` | Filtrar por etiquetas | `--tags URGENTE LIMINAR` |
| `--sem-etiqueta` | Processos sem etiqueta | `--sem-etiqueta` |
| `--prioridade` | Prioritarios (idosos, etc) | `--prioridade` |
| `--sigiloso` | Processos sigilosos | `--sigiloso` |
| `--liminar` | Com pedido de liminar | `--liminar` |
| `--nao-conferidos` | Novos (nao conferidos) | `--nao-conferidos` |
| `--nao-lidos` | Nao lidos | `--nao-lidos` |
| `--polo-ativo` | Nome do autor | `--polo-ativo "JOAO"` |
| `--polo-passivo` | Nome do reu | `--polo-passivo INSS` |
| `--assunto` | Texto no assunto | `--assunto aposentadoria` |
| `--classe` | ID da classe judicial | `--classe 1238` |

### Exemplos de Uso Avancado

**Processos prioritarios de idosos:**
```bash
python3 listar_processos.py --cookies pje_session.json --modo sentenca --prioridade --limite 10
```

**Processos urgentes com liminar:**
```bash
python3 listar_processos.py --cookies pje_session.json --modo decisao --tags URGENTE --liminar
```

**Processos contra o INSS:**
```bash
python3 listar_processos.py --cookies pje_session.json --modo sentenca --polo-passivo INSS
```

**Processos novos nao triados:**
```bash
python3 listar_processos.py --cookies pje_session.json --modo sentenca --sem-etiqueta --nao-conferidos
```

---

## Retorno Esperado

Retorne APENAS:
- Status de cada etapa (sucesso/erro)
- Caminhos dos arquivos gerados
- Quantidade de processos/documentos
- Erros encontrados (se houver)

NAO inclua:
- Output completo dos scripts
- Logs detalhados
- Conteudo dos arquivos

---

## Documentacao

Para casos de borda e detalhes tecnicos, consulte:
- `references/documentacao-completa.md` - Fluxos e troubleshooting
- `references/pje-estrutura-tarefas.md` - Tarefas disponiveis no PJE
- `references/pje-etiquetas-filtros.md` - Lista completa de filtros
- `references/pje-navegacao-avancada.md` - Receitas de uso avancado
