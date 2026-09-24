# Contratos dos artefatos jurídicos

Este diretório contém os contratos JSON independentes do ambiente de execução,
compartilhados por Claude Code e Codex. O catálogo relaciona cada nome lógico de
artefato ao arquivo imutável de seu esquema vigente.

O catálogo abrange contexto processual, classificação documental, linha do
tempo, relatório trabalhista, pedidos, provas, encaminhamento, precedentes,
análise e dispositivo. As regras de domínio que produzem esses artefatos ficam
fora dos esquemas, por exemplo em
`runtime/domain/labor-document-classification.json`.

## Validar os casos de teste canônicos

```bash
python3 scripts/validate_artifact_contracts.py \
  --catalog runtime/contracts/catalog.json \
  --fixtures-root tests/fixtures/contracts
```

A suíte exige ao menos um caso válido e um caso rejeitado para cada contrato
catalogado.

## Validar um artefato gerado

```bash
python3 scripts/validate_artifact_contracts.py \
  --catalog runtime/contracts/catalog.json \
  --contract claim-matrix \
  --document /path/to/claim-matrix.json
```

O código de saída `0` indica validade; `1`, violação do esquema selecionado; e
`2`, impossibilidade de avaliar catálogo, esquema, argumentos ou arquivo de
entrada.

Consulte [`VERSIONING.md`](VERSIONING.md) antes de alterar um esquema ou
adicionar uma migração.

## Classificação documental v2

O catálogo usa `document-classification.v2.schema.json`. A versão 1 aceita
permanece imutável para validação histórica. A migração local v1→v2 preserva
todos os tipos, estados, IDs e regras registrados, inclusive `unknown`; ela não
reclassifica o processo nem substitui a classificação nova feita a partir da
fonte. Um resultado migrado mantém `classifier_version: 1`, enquanto uma nova
classificação pelas regras v2 usa `classifier_version: 2`.

```bash
python3 scripts/migrate_document_classification_v1_to_v2.py \
  --input /protected/input/document-classification.json \
  --output /protected/new-bundle
```

O diretório de saída deve existir, estar fora do repositório e ter permissão
`0700`; o arquivo de entrada deve ter `0600`. A migração cria
`document-classification.json` e `document-classification-migration.json` sem
sobrescrever arquivos, ambos com `0600`. O recibo registra as versões, a versão
da implementação e SHA-256 canônicos da entrada e da saída. Para obter os novos
tipos de certidão e comunicação, é necessário reclassificar a fonte autorizada
e regenerar a linha do tempo e o relatório dependentes; migrar v1 não produz
essa nova interpretação.
