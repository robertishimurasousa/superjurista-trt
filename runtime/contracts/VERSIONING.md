# Política de versionamento e migração dos contratos de artefatos

## Identificação da versão

- Cada artefato contém um inteiro `schema_version`.
- Cada entrada do catálogo declara exatamente um `current_version` e aponta
  para um arquivo versionado e imutável, como `claim-matrix.v1.schema.json`.
- Os leitores validam o artefato pelo contrato lógico selecionado
  explicitamente. Rejeitam contratos desconhecidos, versões futuras e versões
  divergentes do esquema selecionado.
- O pipeline só reutiliza artefatos na versão vigente que também passem nos
  controles determinísticos de conteúdo e atualização.

## Política de alterações

Enquanto um item estiver `IN_REVIEW`, o contrato pode ser corrigido se o
resumo criptográfico e a evidência de aceite forem regenerados. Após o aceite,
o esquema versionado existente torna-se imutável.

Qualquer alteração em esquema aceito que modifique campos obrigatórios,
valores permitidos, significado, regras de identificadores ou validação exige:

1. adicionar novo arquivo de esquema `vN`, sem editar o aceito;
2. adicionar casos válidos e inválidos independentes para a nova versão;
3. adicionar migração determinística se o artefato antigo puder ser atualizado
   com segurança;
4. atualizar o catálogo somente após aprovação dos testes do esquema e da
   migração; e
5. documentar consequências para compatibilidade e custódia no roadmap.

## Regras de migração

- Migrações são etapas explícitas de uma versão, chamadas `vN_to_vNplus1`;
  não há reescrita implícita nem salto de versões.
- A migração deve ser determinística, local e sem chamadas a provedores ou
  modelos.
- Ela grava novo artefato e nunca sobrescreve a origem.
- IDs estáveis de pedidos, provas, fontes, análises e dispositivos são preservados.
- Localizadores das fontes, trechos literais, datas de consulta e registros de
  limitações não podem ser descartados nem enfraquecidos.
- A saída registra contrato lógico, versões de origem e destino, resumos
  criptográficos da entrada e saída e versão da implementação da migração.
- Se a conversão segura for impossível, a migração bloqueia e exige nova
  geração a partir da fonte autorizada, seguida de revisão humana.

## Evidências exigidas

A migração só pode ser aceita quando os testes comprovarem:

- entrada válida na versão antiga gera saída válida na versão nova;
- entrada malformada ou sem suporte semântico é rejeitada;
- execuções repetidas geram saída canônica idêntica em bytes;
- o artefato de origem permanece inalterado; e
- campos essenciais à custódia e identificadores estáveis são preservados.
