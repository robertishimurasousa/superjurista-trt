# Revisão humana do inventário probatório do TRT12

Este registro auxilia a passagem entre o inventariador herdado e a futura
`evidence-matrix.json`. Ele **não** confirma autenticidade, admissibilidade,
valor probatório ou procedência de pedido. A saída do agente é uma lista de
observações a conferir, não uma seleção aprovada.

## Responsabilidades

- Uma pessoa com conhecimento jurídico do caso deve decidir se cada item
  descrito merece ser selecionado, a quais pedidos se relaciona e qual
  proposição e relação serão registradas. Quem não tem esse conhecimento pode
  ajudar na custódia técnica, mas não deve preencher essas conclusões como se
  fossem revisão jurídica.
- O revisor deve abrir o **PDF original**, examinar todas as páginas de cada
  documento e comparar os trechos com a imagem e o contexto. O texto extraído
  pode omitir tabelas, assinatura, carimbo ou informação visual.
- Se um item relevante estiver ausente, registre-o em `missing_item_note` do
  documento. Não force sua inclusão como se tivesse sido inventariado.

## Campos do arquivo protegido

O arquivo `evidence-inventory-review.json` é criado com todas as decisões em
`pending`. Preserve `source_pdf_sha256`, `inventory_index_sha256`, os IDs, as
páginas, os trechos, as descrições, as limitações da fonte e
`source_type` e `proposed_claim_ids`; o validador compara esses campos com o PDF
e as observações originais. `source_type` e `proposed_claim_ids` são sugestões
do agente, não decisões.

Antes de editar o JSON, `prepare_evidence_inventory_review_packet.py
--workspace /protected/path/caso` pode criar um roteiro Markdown privado com
os intervalos de páginas, itens, trechos e limitações para consulta. O roteiro
não é formulário de aceite e não substitui a leitura integral do PDF original.
Como contém trechos dos autos, permaneça com ele no diretório privado e fora
do Git e de serviços externos.

Para cada documento, marque `all_pages_reviewed: true` somente após conferir
suas páginas. Use `missing_item_note` para qualquer omissão e `notes` para
ressalvas adicionais. Para cada item, substitua `pending` por:

| `decision` | Quando usar | Campos a preencher |
|---|---|---|
| `include` | O revisor seleciona o item como candidato à matriz, ainda sem avaliação automática de força probante | `selected_type`, `selected_claim_ids`, `relation`, `proposition`, `reason` e eventuais `limitations` |
| `exclude` | O item não será candidato | `reason`; deixe tipo, seleção, relação e proposição vazios |
| `defer` | A decisão depende de fonte ou conferência adicional | `reason`; deixe tipo, seleção, relação e proposição vazios |

Em `include`, os IDs dos pedidos devem existir na matriz do caso; podem
diferir da sugestão do agente quando o revisor justificar a escolha.
`relation` aceita `supports_claim`, `opposes_claim` ou `neutral_context`.
Preencha `reviewer_name` e `reviewed_at` em UTC no formato
`AAAA-MM-DDTHH:MM:SSZ`. Esses campos são **declarações**, não assinatura ou
verificação de identidade.

## Resultado da conferência

O validador rejeita página não conferida, item sem decisão, pedido inexistente,
trecho alterado, cobertura incompleta e seleção sem justificativa. Ele retorna
`requires_followup` quando há item adiado, omissão anotada ou documento cujo
inventário foi `insufficient`. `reviewed_for_selection` confirma somente que
as declarações e referências têm forma e cobertura coerentes; **não** atesta
que a leitura humana ocorreu nem cria `evidence-matrix.json`.

Quando a revisão declarada estiver completa e sem `requires_followup`, o
comando `build_reviewed_evidence_candidates.py` usa o construtor herdado para
produzir `evidence-matrix-candidates.json` e
`evidence-selection-provenance.json`. Os candidatos recebem `analysis_status:
"pending"` e não registram conflitos automaticamente. A proveniência liga
cada `EVD` ao item `INV`, ao trecho literal e à justificativa da seleção;
exclusões permanecem no registro de revisão. Esses arquivos **não** são a
matriz canônica do pipeline nem substituem validação jurídica da interpretação.

Após a publicação, execute o seguinte comando antes de qualquer uso posterior:

```bash
python3 scripts/verify_reviewed_evidence_candidates.py \
  --workspace /protected/path/caso
```

A conferência somente leitura reconstrói os candidatos e a proveniência a
partir das fontes atuais,
recusando arquivo ausente ou alterado e revisão modificada após a publicação.
Seu resultado confirma consistência técnica, não a identidade do revisor,
exaustividade do inventário ou correção jurídica da seleção.

## Aprovação explícita para a matriz canônica

Depois da conferência técnica, uma pessoa com conhecimento jurídico deve
comparar os candidatos e as exclusões com o PDF original e com a matriz de
pedidos. Se houver trecho omitido, vínculo discutível, pedido sem prova não
examinado ou dúvida sobre a seleção, não aprove: corrija a revisão e gere novos
candidatos, sem sobrescrever os arquivos anteriores.

Somente após essa conferência, prepare manualmente no mesmo diretório privado
o arquivo `evidence-matrix-approval.json`, conforme
`runtime/operations/evidence-matrix-approval.v1.schema.json`. Ele deve ter
permissão `0600` e registrar os SHA-256 exatos de
`evidence-matrix-candidates.json`, `evidence-selection-provenance.json`, PDF e
revisão; `reviewer_name`, `reviewer_role`, `approved_at` em UTC após
`reviewed_at`, `approval_for_pipeline: true` e a lista exata
`acknowledged_uncovered_claim_ids` dos pedidos sem prova selecionada. Use
`shasum -a 256` nos arquivos privados para obter os resumos, sem copiar seu
conteúdo para o terminal ou para o repositório. A identidade e a qualificação
informadas são declarações; este comando não as autentica.

```bash
python3 scripts/promote_reviewed_evidence_matrix.py promote \
  --workspace /protected/path/caso
python3 scripts/promote_reviewed_evidence_matrix.py verify \
  --workspace /protected/path/caso
```

A promoção revalida fontes, candidatos, aprovação e lacunas antes de criar,
sem sobrescrita, `evidence-matrix.json` e
`evidence-matrix-promotion.json` com acesso `0600`. O verificador recompõe o
vínculo e recusa alterações posteriores. O recibo atesta apenas consistência
dos arquivos e aprovação **declarada**; não certifica a qualidade jurídica,
não decide pedidos e não substitui os controles posteriores do pipeline.

Mantenha o arquivo e o PDF fora do Git em diretório privado. Não copie nomes,
contatos ou trechos sensíveis para issues ou comentários públicos.
