---
name: pje-download
description: Baixa processos do PJE via API REST. Use com /baixar-pje ou /baixar-converter.
context: fork
agent: general-purpose
allowed-tools: Bash, Read, Write
---

# Download do PJe — fluxo legado do TRF5

> **Não execute a listagem nem o download legados para o TRT12.** Os scripts
> `.claude/skills/pje-download/scripts/` implementam o funcionamento original
> do TRF5 e são preservados apenas como referência de reuso. Os comandos de
> sanitização e validação do mapa HAR são auxiliares do TRT12, mas não são o
> adaptador de obtenção. A listagem de tarefas e processos do TRT12 depende
> de evidências do provedor revisadas e vinculadas a
> `scripts/pje_task_discovery.py`. Não trate endpoints, nomes de tarefas,
> paginação ou campos do TRF5 como fatos sobre o TRT12.

REGRA PARA O FLUXO LEGADO AUTORIZADO DO TRF5: execute os scripts existentes;
não crie código novo. Esta regra não autoriza executar esses scripts no TRT12.

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

### Criar um mapa HAR sanitizado para revisão

Mantenha o HAR bruto autorizado fora do repositório. O comando abaixo remove
valores e corpos das requisições, mas preserva a estrutura de endpoints,
capacidades e estados de falha necessária ao trabalho no adaptador TRT12:

```bash
python3 scripts/sanitize_pje_har.py \
  --input ~/Downloads/pje_authorized.har \
  --output tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1 \
  --authorized-capture
```

Revise o JSON gerado antes de incluí-lo em um commit. Nunca inclua o HAR bruto
nem `pje_session.json` em um commit.

```bash
python3 scripts/validate_pje_har_map.py \
  --map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1
```

Resolva todas as lacunas funcionais apontadas antes de solicitar a revisão
humana do mapa.

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
