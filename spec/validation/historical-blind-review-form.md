# Formulário de revisão histórica cega do TRT12

Use um formulário por pedido. Conclua a pontuação independente antes de
revelar a decisão de referência ou a origem da saída avaliada. Não inclua
nomes das partes, credenciais ou conteúdo sigiloso bruto neste formulário.

## Identificação da revisão

<!-- field:case_id -->
- ID pseudonimizado do processo:

<!-- field:reviewer_id -->
- ID do revisor:

<!-- field:blind_output_id -->
- ID da saída submetida à revisão cega:

<!-- field:sample_partition -->
- Divisão da amostra (`development` ou `untouched_holdout`):

## Pontuação do pedido

<!-- field:claim_id -->
- ID do pedido:

<!-- field:claim_category -->
- Categoria congelada do pedido:

<!-- field:claim_present_reference -->
- Pedido presente na referência (`yes`, `no` ou `unavailable`):

<!-- field:claim_present_system -->
- Pedido presente na saída do sistema (`yes` ou `no`):

<!-- field:source_locator_correct -->
- Localizador da fonte correto (`yes`, `no`, `not_applicable` ou `unavailable`):

<!-- field:quotation_supported -->
- Todas as citações sujeitas a controle têm suporte (`yes`, `no` ou `not_applicable`):

<!-- field:reasoning_congruent -->
- Fundamentação congruente com fatos, provas e normas (`yes`, `no` ou `unavailable`):

<!-- field:disposition_congruent -->
- Dispositivo congruente com o pedido analisado (`yes`, `no` ou `unavailable`):

<!-- field:calculation_criteria_consistent -->
- Critérios de cálculo coerentes (`yes`, `no`, `not_applicable` ou `unavailable`):

## Registro de defeitos

<!-- field:severity -->
- Gravidade (`critical`, `high`, `medium`, `low` ou `none`):

<!-- operational-field:defect_stage -->
- Etapa responsável (`acquisition`, `classification`, `labor_report`, `claim_matrix`,
  `evidence_matrix`, `issue_routing`, `legal_research`, `claim_analysis`, `disposition`,
  `drafting`, `calculation`, `global_gate` ou `none`):

<!-- field:defect_code -->
- Código do defeito:

<!-- field:defect_description -->
- Descrição do defeito sem texto sensível do processo:

<!-- field:reviewer_confidence -->
- Confiança do revisor (`high`, `medium` ou `low`):

<!-- field:adjudication_required -->
- Arbitragem necessária (`yes` ou `no`):

<!-- operational-field:unavailable_reason -->
- Motivo de indisponibilidade (obrigatório se algum valor for `unavailable`):

## Atestado de revisão cega

<!-- operational-field:blind_scoring_completed -->
- [ ] A pontuação foi concluída antes de revelar o resultado de referência.

<!-- operational-field:output_origin_withheld -->
- [ ] O ambiente de execução ou autor da saída avaliada não foi revelado
  durante a pontuação.
- [ ] Todo item indisponível tem motivo registrado e não foi presumido aprovado.
