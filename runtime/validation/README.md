# Execução da validação histórica

A execução da validação mantém o protocolo congelado separado dos resultados
dos revisores. Identificadores reais de processos, nomes das partes, credenciais
e texto bruto dos autos nunca devem ser armazenados neste diretório nem no Git.

## Entradas congeladas

- `historical-validation-protocol.v1.json` fixa amostra, divisões, categorias,
  escala de gravidade, indicadores e limites de aceite antes de observar os resultados.
- `historical-validation-protocol.v1.schema.json` valida a estrutura do protocolo.
- `../../spec/validation/historical-blind-review-form.md` é o formulário de
  pontuação humana.

## Lotes de revisão

Crie o lote real fora do repositório. Ele deve obedecer a
`historical-review-batch.v1.schema.json`, conter somente identificadores
pseudonimizados e estar vinculado ao resumo exato do protocolo validado. Cada
revisão de pedido registra etapa do defeito, gravidade, motivo de
indisponibilidade quando aplicável e os dois atestados de revisão cega.

O lote contém ainda manifesto pseudonimizado com inventário de pedidos
congelado antes da pontuação. Cada lote possui uma só fase: primeiro 15
processos de desenvolvimento; somente após correções, cinco processos
separados da reserva intocada. O pontuador exige revisão de todos os pedidos do
manifesto. Rejeita revisões duplicadas, categorias posteriores ao congelamento,
defeitos incoerentes, fases misturadas, IDs reutilizados de saídas cegas,
várias saídas para um processo e revisores independentes ausentes.

```bash
python3 scripts/score_historical_reviews.py \
  --batch /protected/path/trt12-historical-review-batch.json \
  --output /protected/path/trt12-historical-review-report.json
```

O relatório é determinístico e obedece a
`historical-review-report.v1.schema.json`. Indicadores de desenvolvimento e
reserva intocada são emitidos separadamente e nunca combinados. Dados
indisponíveis exigem motivo e são excluídos, não presumidos aprovados. Cada
relatório vincula a revisão Git avaliada e contém inventário pseudonimizado de
defeitos por etapa e gravidade. Qualquer defeito crítico ou alto reprova a fase.

Execute os testes de pontuação sem rede com:

```bash
python3 -m unittest tests.test_historical_review_scoring -v
```

Testes sintéticos aprovados comprovam apenas o contrato de pontuação. `VAL-02`
permanece incompleto até a revisão cega dos 15 processos de desenvolvimento
autorizados por profissional qualificado designado; os outros cinco pertencem
exclusivamente à reserva posterior de `VAL-03`.

## Correção e reserva intocada

Após a revisão dos 15 processos, registre cada correção fora do repositório
usando `historical-correction-register.v1.schema.json`. Cada entrada preserva ID
pseudonimizado do defeito, etapa, gravidade, código, commit de correção, resumo
da medida e evidência de regressão aprovada. Os cinco processos da reserva
ficam sem pontuação até o congelamento das correções em nova revisão do sistema.

Valide as correções e a reserva separada aprovada com:

```bash
python3 scripts/validate_historical_rerun.py \
  --development-report /protected/path/development-report.json \
  --correction-register /protected/path/correction-register.json \
  --holdout-report /protected/path/holdout-report.json \
  --output /protected/path/historical-rerun-report.json
```

O validador exige correção de cada defeito crítico/alto de desenvolvimento,
preserva seus campos de custódia, rejeita correções abertas ou reprovadas,
confere os indicadores contra os limites congelados, vincula revisões inicial e
corrigida e aceita apenas uma reserva distinta de cinco processos aprovada.

## Dossiê de aceite

Depois de `VAL-03`, prepare revisão humana sem segredos conforme
`historical-dossier-review.v1.schema.json`. Ela registra limitações, falhas
observadas ou potenciais, medidas de mitigação, recomendação de seguir/não
seguir, motivos e decisão explícita pendente, aprovada ou rejeitada. Monte o
dossiê vinculado às evidências com:

```bash
python3 scripts/build_historical_acceptance_dossier.py \
  --development-report /protected/path/development-report.json \
  --holdout-report /protected/path/holdout-report.json \
  --rerun-report /protected/path/historical-rerun-report.json \
  --dossier-review /protected/path/dossier-review.json \
  --output /protected/path/historical-acceptance-dossier.json
```

O montador verifica protocolo, resumos dos relatórios, fases, revisões inicial e
corrigida, defeitos materiais da reserva e identidade da aprovação. Decisão
pendente permanece `pending_approval`; rejeição ou recomendação `no_go`
permanece `no_go`. Mesmo aprovado, o dossiê limita-se a verificação prévia
local, supervisionada por pessoa e específica do processo, mantendo atos
judiciais externos desabilitados.
