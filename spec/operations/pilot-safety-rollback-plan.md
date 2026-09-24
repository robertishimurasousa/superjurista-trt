# Plano de segurança e reversão do piloto controlado do TRT12

**Situação:** aprovado; a execução do processo permanece `NO-GO` até passar na
verificação prévia específica do caso

**Escopo:** piloto local e supervisionado do primeiro grau do TRT12

**Atos judiciais externos:** proibidos

## 1. Objetivo de segurança

O piloto pode obter material autorizado, produzir artefatos locais rastreáveis,
pesquisar fontes oficiais e gerar uma minuta para avaliação. Não pode
protocolar, assinar, publicar, mover tarefa no PJe, enviar mensagem, alterar
processo ou praticar qualquer outro ato judicial externo.

O operador deve poder interromper a execução em qualquer etapa. Fonte ausente,
provedor indisponível, controle reprovado, checkpoint vencido, divergência de
integridade ou defeito crítico/alto não resolvido constituem resultados finais
válidos e nunca podem ser convertidos em aprovação.

## 2. Elegibilidade do piloto

O primeiro piloto controlado limita-se a um processo autorizado do primeiro
grau do TRT12. Enquanto não houver aprovação para dados mais sensíveis, esse
processo não pode ser sigiloso nem exigir tratamento excepcional de acesso.

Antes da importação, registre fora do Git:

- alcance da autorização e operador;
- classificação de acesso ao processo;
- conjunto documental esperado e localização da fonte local;
- prazo de retenção específico do processo;
- saídas pretendidas e responsável pela revisão;
- provedores de modelo autorizados a receber os dados estruturados do processo;
- identificador exato do modelo aprovado para cada despacho;
- confirmação explícita de que não se solicita protocolo nem movimentação no PJe.

O piloto é inelegível se qualquer desses campos estiver ausente.

## 3. Papéis e separação de responsabilidades

| Papel | Responsabilidade | Responsável proposto |
|---|---|---|
| Operador | Inicia, observa, interrompe e registra a execução local delimitada | Titular do repositório |
| Revisor jurídico | Revisa pedidos, provas, autoridades, fundamentação, cálculos e minuta | Profissional qualificado identificado |
| Responsável por incidentes | Coordena contenção, preservação, correção e encerramento | Titular do repositório |
| Responsável pelos dados | Aprova classificação, retenção e exclusão segura | Titular do repositório |

Uma pessoa pode acumular operação, resposta a incidentes e responsabilidade
pelos dados no uso pessoal. A revisão jurídica continua sendo uma etapa
distinta de julgamento humano, mesmo que o titular seja profissional do
Direito. Nenhum controle automático substitui essa revisão.

## 4. Tratamento dos dados e retenção proposta

Os prazos abaixo são padrões conservadores do piloto e exigem aprovação
explícita antes do primeiro processo real:

| Classe de dados | Local | Retenção proposta | Descarte |
|---|---|---|---|
| Credenciais, cookies, cabeçalhos e MFA | Memória ou armazenamento local de sessão ignorado | Fim da sessão autenticada | Revogar sessão e remover estado local com segurança |
| Captura HAR bruta autorizada | Fora do repositório | Excluir após revisão do mapa sanitizado; máximo de 24 horas | Exclusão local segura |
| Mapa sanitizado de endpoints | Versionado somente após revisão humana | Enquanto a evidência estiver atual | Remover ou substituir quando invalidado |
| Documentos processuais brutos | Armazenamento local criptografado e ignorado | Prazo por processo; máximo proposto de 30 dias após revisão | Exclusão segura e registro de custódia |
| Artefatos derivados e minuta | Armazenamento local criptografado e ignorado | Prazo por processo; máximo proposto de 90 dias após revisão | Exclusão segura e registro de custódia |
| Resumo de ensaios e incidentes sem segredos | Registro operacional local protegido | Proposta de 180 dias | Descarte normal do registro protegido |
| Dados e relatórios sintéticos de teste | Repositório | Enquanto os contratos forem suportados | Ciclo normal de versionamento |

Se dever legal, institucional, de preservação ou auditoria exigir prazo
distinto, ele prevalece e deve ser registrado antes do processamento. Não se
pode ampliar o prazo apenas por conveniência.

## 5. Verificação prévia obrigatória

O operador deve concluir o manual de operação aceito e registrar:

- commit exato em `development`;
- situação de prontidão e resumo criptográfico do host;
- controle de qualidade aprovado;
- resumos sintéticos idênticos e aprovados de Claude Code e Codex;
- classificação dos dados e prazo de retenção aprovados;
- mapa TRT12 sanitizado e revisado;
- espaço local de trabalho fora dos caminhos versionados;
- revisor jurídico identificado;
- confirmação de que o controle global será aplicado.

Qualquer item ausente resulta em `NO-GO`.

## 6. Controles da execução

- Processar um processo por vez durante o piloto.
- Limitar páginas, tamanho das respostas, tentativas e tempo de espera.
- Persistir apenas checkpoints versionados e vinculados à requisição, ao
  catálogo, aos contratos e aos resumos criptográficos atuais.
- Conferir cada conteúdo baixado com o SHA-256 indexado antes de usá-lo.
- Preservar explicitamente estados indisponíveis, desconhecidos, conflitantes
  e de abstenção.
- Usar fontes jurídicas oficiais HTTPS e guardar localizadores e fidelidade
  das citações.
- Nunca repetir sessão expirada, não autorizada ou sujeita a MFA como válida.
- Nunca ampliar o limite de tentativas persistido para forçar conclusão.
- Nunca continuar após reprovação do controle global.
- Nunca colocar autos brutos, credenciais ou estado de navegador autenticado
  no Git ou na CI.
- Não despachar autos reais ao Codex CLI neste host até comprovar a restrição
  das ferramentas residuais e do acesso a arquivos locais, ou usar outro
  transporte de modelo sem ferramentas com autorização específica.
- Manter a recusa de insumos diferentes da amostra sintética no orquestrador,
  relator e triador atuais; só substituir esse limite após validar o novo
  transporte e repetir os testes de segurança com autorização específica.

## 7. Controle de revisão humana

O revisor jurídico deve examinar todos os artefatos antes que a minuta seja
considerada utilizável:

1. todos os pedidos e providências requeridas estão representados;
2. todas as defesas relevantes e suas ausências estão explícitas;
3. cada alegação relevante tem localizador correto da fonte;
4. citações e autoridades têm suporte em fontes oficiais custodiadas;
5. critérios de cálculo correspondem ao dispositivo;
6. análise, resultado, dispositivo e minuta são congruentes;
7. limitações, indisponibilidades e abstenções estão visíveis;
8. nenhum defeito crítico ou alto permanece;
9. a minuta não contém instrução nem mecanismo para ato judicial externo.

A aprovação vale apenas para o processo revisado. Não certifica casos futuros
nem adequação jurídica geral.

## 8. Classificação de incidentes

| Gravidade | Exemplos | Resposta imediata |
|---|---|---|
| Crítica | Exposição de credencial ou dados sigilosos; ato externo não previsto; autoridade inventada; pedido material omitido do dispositivo | Parar, isolar, revogar acesso, preservar evidência sem segredos e avisar responsáveis |
| Alta | Erro material de pedido, prova, norma, cálculo ou dispositivo com potencial de alterar o resultado | Parar, pôr saídas em quarentena, invalidar checkpoints dependentes e abrir revisão corretiva |
| Média | Fundamentação incompleta ou imprecisa sem efeito decisório independente | Bloquear aprovação, corrigir e repetir etapas e controles afetados |
| Baixa | Problema localizado de estilo, clareza ou formatação | Registrar e corrigir antes da revisão final, quando viável |

Incidentes críticos e altos têm tolerância zero para aceite.

## 9. Contenção e reversão

Em caso de incidente crítico/alto ou falha de integridade:

1. interromper o processo e não repetir acesso externo;
2. desconectar ou revogar a sessão e trocar credenciais expostas no sistema
   responsável;
3. mover o espaço local para quarentena protegida, sem adicioná-lo ao Git;
4. registrar commit, etapa, resumo do checkpoint, estado do provedor, IDs dos
   artefatos afetados e horários, sem copiar dados sensíveis;
5. invalidar a etapa afetada e todos os checkpoints dependentes;
6. restaurar código apenas de commit aprovado em `development`, sem sobrescrever
   alterações de outras pessoas;
7. corrigir o defeito específico e adicionar evidência de regressão;
8. repetir controles de qualidade, teste sintético nos dois ambientes e
   verificações do processo afetado, com saídas limpas;
9. exigir aprovação jurídica antes de retirar o material da quarentena;
10. encerrar o incidente apenas após documentar contenção, correção,
    verificação, retenção e exclusão.

Reversão significa voltar ao último estado local verificado. Nunca significa
alterar ou desfazer ato judicial no PJe, pois o piloto não pode praticá-lo.

## 10. Decisão de recuperação

A retomada só é permitida quando todas as condições abaixo forem verdadeiras:

- autorização e sessão continuam válidas;
- requisição e catálogo não mudaram;
- bytes aceitos ainda correspondem aos resumos armazenados;
- limite de tentativas não foi esgotado;
- contratos e controles atuais aceitam o checkpoint;
- responsável pelo incidente liberou o espaço de trabalho;
- nenhum defeito crítico/alto permanece.

Caso contrário, abandone o checkpoint e inicie nova execução autorizada com
saídas limpas. Preserve o espaço anterior apenas pelo prazo de retenção
aprovado para o incidente.

## 11. Decisão de seguir/não seguir e responsabilidade pelo suporte

O piloto só pode começar após completar o registro de aprovação abaixo. No uso
pessoal, o suporte é feito conforme a disponibilidade do titular do repositório;
não há acordo de nível de serviço de produção. Uso por outro operador ou
unidade exige nova decisão sobre suporte, acesso, treinamento e escalonamento
de incidentes.

### Registro de aprovação

```text
Versão/commit do plano: 0.1 / aprovação registrada em development
Operador aprovado: titular do repositório
Revisor jurídico aprovado: profissional qualificado identificado antes da liberação de cada caso
Responsável por incidentes: titular do repositório
Responsável pelos dados: titular do repositório
Retenção de HAR bruto: excluir após revisão do mapa; máximo de 24 horas
Retenção de documentos brutos: prazo por caso; máximo de 30 dias após revisão
Retenção de artefatos derivados: prazo por caso; máximo de 90 dias após revisão
Retenção de resumo de incidentes: máximo de 180 dias
Classificação do primeiro caso: processo autorizado e não sigiloso do primeiro grau TRT12
Data da aprovação: 2026-09-21
Aprovador: titular do repositório
Decisão: NO-GO até concluir a verificação prévia específica do caso
Condições/exceções: sem atos judiciais externos; autorização e revisor jurídico obrigatórios
```

Esta aprovação aceita políticas de segurança, responsabilidade, retenção e
reversão; não autoriza processo não identificado. Cada piloto com processo real
permanece `NO-GO` até que autorização, classificação, prazo de retenção,
revisor jurídico e mapa sanitizado de endpoints revisado constem da
verificação prévia específica do caso.
