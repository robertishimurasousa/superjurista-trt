# Inventário de reuso do fork

O inventário de reuso legível por máquina está em
[`superjurista-fork-reuse-ledger.json`](superjurista-fork-reuse-ledger.json).

Ele é gerado a partir do fork atual por:

```bash
python3 scripts/build_reuse_ledger.py \
  --root . \
  --output spec/inventory/superjurista-fork-reuse-ledger.json
```

## Resumo da situação atual

| Tratamento | Componentes |
|---|---:|
| Preservar | 1 |
| Adaptar | 84 |
| Substituir | 6 |
| Retirar do caminho executável do TRT12 | 18 |
| **Total** | **109** |

Segundo o detector de vínculos, 50 componentes dependem explicitamente do
ambiente Claude e 59 são atualmente independentes do ambiente de execução.
`Retire` não autoriza apagar arquivos. O componente permanece no repositório
até que verificações de dependências mostrem que nenhum fluxo TRT12 aceito o exige.

Cada entrada registra o tipo de componente, o tratamento na migração, a
justificativa, as dependências detectadas de ambiente de execução e o SHA-256
do arquivo-fonte. Todo componente novo abrangido pelo inventário deve ser
classificado antes de ele voltar ao estado aceito.
