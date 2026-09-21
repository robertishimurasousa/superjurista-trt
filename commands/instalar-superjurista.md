# Command: instalar-superjurista v1.0

> **Propósito:** Instala o SuperJurista no projeto atual, copiando pipelines, agentes, skills e estrutura completa para processamento de processos judiciais
>
> **Tipo:** Command direto (executa fases sequencialmente, sem delegação a subagentes)

---
description: Instala o SuperJurista no projeto atual - copia pipelines, agentes, skills e estrutura completa para processamento de processos judiciais
argument-hint: (sem argumentos)
allowed-tools: Bash Read Write AskUserQuestion Glob
---

<identidade>
  <papel>Instalador do SuperJurista - responsável por copiar o scaffold completo para o projeto do usuário</papel>
  <estilo>Metódico, cauteloso com arquivos existentes, informativo sobre o que está fazendo</estilo>
</identidade>

<proposito>
  <objetivo>Instalar todos os componentes do SuperJurista (commands, agents, skills, mcp-servers, estrutura de dados) no diretório atual do usuário, respeitando arquivos já existentes</objetivo>
  <razao>A instalação manual seria trabalhosa e propensa a erros. Este command garante que a estrutura completa seja copiada corretamente, com tratamento de conflitos e validação.</razao>
  <resultado_final>Projeto configurado com todos os artefatos do SuperJurista, pronto para uso dos pipelines</resultado_final>
</proposito>

<restricoes>
  - NUNCA sobrescrever arquivos sem confirmação explícita do usuário
  - NUNCA copiar diretórios __pycache__ ou outros artefatos de build
  - NUNCA modificar o CLAUDE.md existente sem permissão
  - SEMPRE usar ${CLAUDE_PLUGIN_ROOT} para referenciar o scaffold
  - SEMPRE mostrar resumo final com componentes instalados
  - SEMPRE usar português brasileiro com acentos corretos
</restricoes>

<contingencias>
  <se_scaffold_ausente>
    Verificar se ${CLAUDE_PLUGIN_ROOT}/scaffold/ existe.
    Se NÃO existir → informar erro: "Diretório scaffold não encontrado em ${CLAUDE_PLUGIN_ROOT}/scaffold/. Verifique a instalação do plugin."
    → Abortar instalação
  </se_scaffold_ausente>

  <se_permissao_negada>
    Se qualquer operação de cópia falhar com "Permission denied":
    → Informar o usuário sobre o erro de permissão
    → Sugerir executar com permissões elevadas
    → Abortar instalação
  </se_permissao_negada>

  <se_copia_parcial>
    Se cópia falhar no meio do processo:
    → Informar quais diretórios foram copiados com sucesso
    → Informar quais falharam
    → Sugerir re-executar /instalar-superjurista
  </se_copia_parcial>
</contingencias>

<!-- ═══════════════════════════════════════════════════════════════════════════════ -->
<!-- FASES DA INSTALAÇÃO                                                            -->
<!-- ═══════════════════════════════════════════════════════════════════════════════ -->

<fases_pipeline>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FASE 1: VERIFICAÇÃO DO AMBIENTE                                -->
  <!-- ═══════════════════════════════════════════════════════════════ -->

  <fase numero="1" nome="Verificação do Ambiente">
    <objetivo>Verificar se o diretório atual é adequado para instalação e detectar conflitos</objetivo>

    <acao>
      1. **Verificar se o scaffold existe:**
         ```bash
         ls ${CLAUDE_PLUGIN_ROOT}/scaffold/commands/ > /dev/null 2>&1
         ```
         Se falhar → abortar com mensagem de erro (ver contingência se_scaffold_ausente)

      2. **Verificar instalação existente:**
         Usar Glob para checar se `.claude/commands/` já tem arquivos:
         ```
         Glob: .claude/commands/*.md
         ```

      3. **Se .claude/commands/ já existe E contém arquivos .md:**
         Usar AskUserQuestion para perguntar ao usuário:

         ```
         O diretório .claude/ já existe neste projeto e contém arquivos.
         Como deseja prosseguir?

         (A) Sobrescrever tudo - substitui todos os arquivos existentes
         (B) Mesclar - copia apenas arquivos que não existem (preserva alterações)
         (C) Cancelar - abortar instalação
         ```

         Armazenar a escolha do usuário como $MODO_COPIA:
         - Se (A) → $MODO_COPIA = "sobrescrever"
         - Se (B) → $MODO_COPIA = "mesclar"
         - Se (C) → informar "Instalação cancelada pelo usuário." e PARAR

      4. **Se .claude/ não existe ou está vazio:**
         ```
         $MODO_COPIA = "instalar"
         ```
         Prosseguir diretamente (instalação limpa)

      5. **Validar o runtime Python do núcleo:**
         ```bash
         command -v python3 > /dev/null 2>&1 && \
           python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
         ```
         Se falhar → informar que o núcleo requer Python 3.9+ e abortar sem copiar arquivos.
    </acao>
  </fase>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FASE 2: CÓPIA DO SCAFFOLD                                      -->
  <!-- ═══════════════════════════════════════════════════════════════ -->

  <fase numero="2" nome="Cópia do Scaffold">
    <objetivo>Copiar commands, agents, skills e mcp-servers do scaffold para o projeto</objetivo>

    <acao>
      1. **Criar diretórios base:**
         ```bash
         mkdir -p .claude/commands .claude/agents .claude/skills .claude/mcp-servers scripts requirements runtime
         ```
         (`scripts/` na RAIZ do projeto — é onde vive o motor de gate `verificar_pipeline.py`
         que os pipelines v3.0 importam; não é `.claude/scripts/`.)

      2. **Copiar conteúdo conforme $MODO_COPIA:**

         <se_modo_sobrescrever_ou_instalar>
           Cópia completa (substitui tudo):
           ```bash
           cp -r "${CLAUDE_PLUGIN_ROOT}/scaffold/commands/"* .claude/commands/
           cp -r "${CLAUDE_PLUGIN_ROOT}/scaffold/agents/"* .claude/agents/
           cp -r "${CLAUDE_PLUGIN_ROOT}/scaffold/skills/"* .claude/skills/
           cp -r "${CLAUDE_PLUGIN_ROOT}/scaffold/mcp-servers/"* .claude/mcp-servers/
           cp -r "${CLAUDE_PLUGIN_ROOT}/scaffold/scripts/"* scripts/   # motor de gate v3.0 (verificar_pipeline.py)
           cp -r "${CLAUDE_PLUGIN_ROOT}/requirements/"* requirements/
           cp -r "${CLAUDE_PLUGIN_ROOT}/runtime/"* runtime/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/check_python_contract.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/check_data_hygiene.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/build_claim_matrix.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/build_claim_decisions.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/build_evidence_matrix.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/build_issue_routes.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/build_labor_report.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/classify_labor_documents.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/provider_interfaces.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/pje_session_adapter.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/pje_task_discovery.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/sanitize_pje_har.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/schema_validation.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/validate_pje_har_map.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifact_contracts.py" scripts/
           cp "${CLAUDE_PLUGIN_ROOT}/scripts/validate_tribunal_profile.py" scripts/
           ```
         </se_modo_sobrescrever_ou_instalar>

         <se_modo_mesclar>
           Cópia sem sobrescrever (preserva arquivos existentes):
           ```bash
           cp -rn "${CLAUDE_PLUGIN_ROOT}/scaffold/commands/"* .claude/commands/
           cp -rn "${CLAUDE_PLUGIN_ROOT}/scaffold/agents/"* .claude/agents/
           cp -rn "${CLAUDE_PLUGIN_ROOT}/scaffold/skills/"* .claude/skills/
           cp -rn "${CLAUDE_PLUGIN_ROOT}/scaffold/mcp-servers/"* .claude/mcp-servers/
           cp -rn "${CLAUDE_PLUGIN_ROOT}/scaffold/scripts/"* scripts/   # motor de gate v3.0 (verificar_pipeline.py)
           cp -rn "${CLAUDE_PLUGIN_ROOT}/requirements/"* requirements/
           cp -rn "${CLAUDE_PLUGIN_ROOT}/runtime/"* runtime/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/check_python_contract.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/check_data_hygiene.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/build_claim_matrix.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/build_claim_decisions.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/build_evidence_matrix.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/build_issue_routes.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/build_labor_report.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/classify_labor_documents.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/provider_interfaces.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/pje_session_adapter.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/pje_task_discovery.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/sanitize_pje_har.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/schema_validation.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/validate_pje_har_map.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifact_contracts.py" scripts/
           cp -n "${CLAUDE_PLUGIN_ROOT}/scripts/validate_tribunal_profile.py" scripts/
           ```
           (A flag -n / --no-clobber impede sobrescrita de arquivos existentes)
         </se_modo_mesclar>

      3. **Limpar artefatos de build copiados acidentalmente:**
         ```bash
         find .claude/ -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
         ```

      4. **Verificar sucesso:**
         Checar se os diretórios principais foram populados:
         ```bash
         ls .claude/commands/*.md > /dev/null 2>&1 && echo "commands OK" || echo "commands FALHOU"
         ls .claude/agents/analise/*.md > /dev/null 2>&1 && echo "agents OK" || echo "agents FALHOU"
         ls .claude/skills/pje-download/SKILL.md > /dev/null 2>&1 && echo "skills OK" || echo "skills FALHOU"
         ls .claude/mcp-servers/tjsc-eproc/server.py > /dev/null 2>&1 && echo "mcp-servers OK" || echo "mcp-servers FALHOU"
         ls .claude/mcp-servers/tnu-eproc/server.py > /dev/null 2>&1 && echo "mcp tnu OK" || echo "mcp tnu FALHOU"
         ls scripts/verificar_pipeline.py > /dev/null 2>&1 && echo "scripts OK" || echo "scripts FALHOU"
         ls requirements/runtime.txt > /dev/null 2>&1 && echo "requirements OK" || echo "requirements FALHOU"
         ls runtime/python-contract.json > /dev/null 2>&1 && echo "runtime contract OK" || echo "runtime contract FALHOU"
         ls scripts/check_python_contract.py > /dev/null 2>&1 && echo "python contract checker OK" || echo "python contract checker FALHOU"
         ls scripts/check_data_hygiene.py > /dev/null 2>&1 && echo "data hygiene checker OK" || echo "data hygiene checker FALHOU"
         ls scripts/build_claim_matrix.py > /dev/null 2>&1 && echo "claim matrix builder OK" || echo "claim matrix builder FALHOU"
         ls scripts/build_claim_decisions.py > /dev/null 2>&1 && echo "claim decision builder OK" || echo "claim decision builder FALHOU"
         ls scripts/build_evidence_matrix.py > /dev/null 2>&1 && echo "evidence matrix builder OK" || echo "evidence matrix builder FALHOU"
         ls scripts/build_issue_routes.py > /dev/null 2>&1 && echo "issue router OK" || echo "issue router FALHOU"
         ls scripts/build_labor_report.py > /dev/null 2>&1 && echo "labor report builder OK" || echo "labor report builder FALHOU"
         ls scripts/classify_labor_documents.py > /dev/null 2>&1 && echo "labor document classifier OK" || echo "labor document classifier FALHOU"
         ls scripts/provider_interfaces.py > /dev/null 2>&1 && echo "provider interfaces OK" || echo "provider interfaces FALHOU"
         ls scripts/pje_session_adapter.py > /dev/null 2>&1 && echo "PJe session classifier OK" || echo "PJe session classifier FALHOU"
         ls scripts/pje_task_discovery.py > /dev/null 2>&1 && echo "PJe task discovery OK" || echo "PJe task discovery FALHOU"
         ls scripts/sanitize_pje_har.py > /dev/null 2>&1 && echo "HAR sanitizer OK" || echo "HAR sanitizer FALHOU"
         ls scripts/schema_validation.py > /dev/null 2>&1 && echo "schema validator core OK" || echo "schema validator core FALHOU"
         ls scripts/validate_pje_har_map.py > /dev/null 2>&1 && echo "HAR map validator OK" || echo "HAR map validator FALHOU"
         ls scripts/validate_artifact_contracts.py > /dev/null 2>&1 && echo "artifact contract checker OK" || echo "artifact contract checker FALHOU"
         ls scripts/validate_tribunal_profile.py > /dev/null 2>&1 && echo "tribunal profile checker OK" || echo "tribunal profile checker FALHOU"
         ls runtime/profiles/trt12.json > /dev/null 2>&1 && echo "TRT12 profile OK" || echo "TRT12 profile FALHOU"
         ls runtime/providers/interfaces.json > /dev/null 2>&1 && echo "provider contract OK" || echo "provider contract FALHOU"
         ls runtime/providers/har-sanitization-contract.json > /dev/null 2>&1 && echo "HAR sanitization contract OK" || echo "HAR sanitization contract FALHOU"
         ls runtime/providers/har-map-review-contract.json > /dev/null 2>&1 && echo "HAR review contract OK" || echo "HAR review contract FALHOU"
         ls runtime/providers/pje-session-contract.json > /dev/null 2>&1 && echo "PJe session contract OK" || echo "PJe session contract FALHOU"
         ls runtime/providers/pje-task-discovery-contract.json > /dev/null 2>&1 && echo "PJe task discovery contract OK" || echo "PJe task discovery contract FALHOU"
         ls runtime/domain/labor-document-classification.json > /dev/null 2>&1 && echo "labor document classification contract OK" || echo "labor document classification contract FALHOU"
         ls runtime/domain/labor-claim-taxonomy.json > /dev/null 2>&1 && echo "labor claim taxonomy OK" || echo "labor claim taxonomy FALHOU"
         ```
         Se qualquer um falhou → reportar erro e parar

      5. **Validar o perfil TRT12 instalado:**
         ```bash
         python3 scripts/validate_tribunal_profile.py \
           --schema runtime/profiles/schema.json \
           --registry runtime/profiles/registry.json \
           --profile runtime/profiles/trt12.json
         ```
         Se falhar → não declarar a instalação pronta. Corrigir o contrato ou restaurar os
         arquivos canônicos antes de executar qualquer pipeline.

      6. **Validar o contrato de interfaces de provedores:**
         ```bash
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from provider_interfaces import load_provider_interfaces; load_provider_interfaces(Path('runtime/providers/interfaces.json')); print('[OK] provider interface contract')"
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from pje_session_adapter import load_session_contract; load_session_contract(Path('runtime/providers/pje-session-contract.json')); print('[OK] PJe session contract')"
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from pje_task_discovery import load_task_discovery_contract; load_task_discovery_contract(Path('runtime/providers/pje-task-discovery-contract.json')); print('[OK] PJe task discovery contract')"
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from build_claim_matrix import load_claim_taxonomy; load_claim_taxonomy(Path('runtime/domain/labor-claim-taxonomy.json')); print('[OK] labor claim taxonomy')"
         PYTHONPATH=scripts python3 -c "from build_claim_decisions import build_claim_analysis, build_disposition_matrix, render_judgment_draft; print('[OK] claim decision builder')"
         PYTHONPATH=scripts python3 -c "from build_evidence_matrix import build_evidence_matrix; print('[OK] evidence matrix builder')"
         PYTHONPATH=scripts python3 -c "from build_issue_routes import build_issue_routes; print('[OK] issue router')"
         PYTHONPATH=scripts python3 -c "from build_labor_report import build_labor_report; print('[OK] labor report builder')"
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from classify_labor_documents import load_classification_contract; load_classification_contract(Path('runtime/domain/labor-document-classification.json')); print('[OK] labor document classification contract')"
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from sanitize_pje_har import load_sanitization_contract; load_sanitization_contract(Path('runtime/providers/har-sanitization-contract.json')); print('[OK] HAR sanitization contract')"
         PYTHONPATH=scripts python3 -c "from pathlib import Path; from validate_pje_har_map import load_review_contract; load_review_contract(Path('runtime/providers/har-map-review-contract.json')); print('[OK] HAR map review contract')"
         ```
         Se falhar → não declarar a instalação pronta. Nenhum adaptador PJe ou de pesquisa
         pode executar sem o manifesto canônico válido.

      7. **Validar o runtime dos MCPs:**
         ```bash
         python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
         ```
         Se falhar → NÃO registrar os MCPs. Continuar a instalação do núcleo e incluir
         no resumo que os MCPs locais permanecem desabilitados até Python 3.10+ estar ativo.

      8. **Registrar os MCPs no `.mcp.json` da raiz (caminho absoluto):**
         Sem este registro os servidores NÃO carregam. NÃO usar settings.json — config
         de MCP ali é padrão antigo e falha silenciosamente. O merge abaixo é idempotente
         (preserva servidores já registrados pelo usuário):
         ```bash
         python3 -c "import json,os;raiz=os.path.abspath('.');S=['bnp-api','cjf-jurisprudencia','tcu-jurisprudencia','tjsc-eproc','tnu-eproc'];cfg=json.load(open('.mcp.json',encoding='utf-8')) if os.path.exists('.mcp.json') else {};m=cfg.setdefault('mcpServers',{});novos=[s for s in S if s not in m];[m.__setitem__(s,{'command':'python3','args':[os.path.join(raiz,'.claude','mcp-servers',s,'server.py')]}) for s in novos];json.dump(cfg,open('.mcp.json','w',encoding='utf-8'),indent=2,ensure_ascii=False);print('[OK] .mcp.json: '+str(len(novos))+' registrados agora, '+str(len(m))+' no total')"
         ```
         (Testado e idempotente. Se o one-liner falhar no shell do usuário, gerar o
         `.mcp.json` via Write com as mesmas 5 entradas e caminho absoluto.)
         Avisar: os MCPs só carregam em SESSÃO NOVA do Claude Code.
    </acao>
  </fase>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FASE 3: ARQUIVOS RAIZ                                          -->
  <!-- ═══════════════════════════════════════════════════════════════ -->

  <fase numero="3" nome="Arquivos Raiz">
    <objetivo>Instalar CLAUDE.md, README.md e .gitignore na raiz do projeto</objetivo>

    <acao>
      1. **CLAUDE.md:**
         - Verificar se `./CLAUDE.md` já existe
         - Se NÃO existe:
           ```bash
           cp "${CLAUDE_PLUGIN_ROOT}/scaffold/project-claude.md" ./CLAUDE.md
           ```
         - Se já existe:
           Usar AskUserQuestion:
           ```
           O arquivo CLAUDE.md já existe neste projeto.
           Como deseja prosseguir?

           (A) Substituir pelo CLAUDE.md do SuperJurista
           (B) Anexar configurações do SuperJurista ao final do arquivo existente
           (C) Pular - manter o CLAUDE.md atual sem alterações
           ```
           - Se (A): copiar sobrescrevendo
           - Se (B): usar Bash para ler o conteúdo de ${CLAUDE_PLUGIN_ROOT}/scaffold/project-claude.md e
             fazer append no CLAUDE.md existente, separando com uma linha `---` e cabeçalho
             `## SuperJurista - Configuração Adicionada`
           - Se (C): pular

      2. **README.md:**
         - Verificar se `./README.md` já existe
         - Se NÃO existe:
           ```bash
           cp "${CLAUDE_PLUGIN_ROOT}/scaffold/project-readme.md" ./README.md
           ```
         - Se já existe: pular silenciosamente (não sobrescrever README do usuário)

      3. **.gitignore:**
         - Verificar se `./.gitignore` já existe
         - Se NÃO existe:
           ```bash
           cp "${CLAUDE_PLUGIN_ROOT}/scaffold/project-gitignore" ./.gitignore
           ```
         - Se já existe: preservar todas as linhas atuais e acrescentar somente os padrões
           ausentes exigidos por `runtime/data-hygiene-contract.json`. Nunca remover ou
           sobrescrever regras do usuário.

      4. **Validar higiene de dados:**
         ```bash
         python3 scripts/check_data_hygiene.py \
           --root . \
           --contract runtime/data-hygiene-contract.json
         ```
         Se falhar → não declarar a instalação pronta. Informar somente arquivo, linha e
         identificador da regra; nunca exibir o conteúdo sensível detectado.
    </acao>
  </fase>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FASE 4: ESTRUTURA DE DADOS                                     -->
  <!-- ═══════════════════════════════════════════════════════════════ -->

  <fase numero="4" nome="Estrutura de Dados">
    <objetivo>Criar diretórios para armazenamento de processos</objetivo>

    <acao>
      ```bash
      mkdir -p data/sentenca data/decisao
      ```

      Esses diretórios são onde os processos baixados e seus artefatos serão armazenados:
      - `data/sentenca/` - processos aguardando sentença
      - `data/decisao/` - processos aguardando decisão interlocutória
    </acao>
  </fase>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FASE 5: RESUMO                                                  -->
  <!-- ═══════════════════════════════════════════════════════════════ -->

  <fase numero="5" nome="Resumo">
    <objetivo>Exibir resumo completo da instalação</objetivo>

    <acao>
      Exibir o seguinte resumo para o usuário (contar arquivos reais copiados via Bash se possível):

      ```
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      SuperJurista instalado com sucesso!
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

      Componentes instalados:
        16 comandos (pipelines e utilitarios)
        49 agentes (7 categorias: analise, extracao, pesquisa, redacao, revisao, lista-trf, tribunal)
        6 skills (download PJE, conversao PDF, captura sessao, analise probatoria, erro medico, terminal)
        5 servidores MCP (BNP/CNJ, CJF Unificada, TCU, TJSC eProc, TNU eProc)
        Registro automatico no .mcp.json (carregam na PROXIMA sessao)

      Estrutura criada:
        .claude/commands/    -- pipelines e comandos
        .claude/agents/      -- agentes especializados
        .claude/skills/      -- skills com scripts
        .claude/mcp-servers/ -- servidores MCP locais
        .mcp.json            -- registro dos MCPs (caminho absoluto)
        scripts/             -- motor de gate v3.0 (verificar_pipeline.py)
        requirements/        -- dependencias Python versionadas
        runtime/             -- contratos neutros de Python e execução
        data/sentenca/       -- processos para sentenca
        data/decisao/        -- processos para decisao

      Dependencias externas necessarias:
        Python 3.9+ para o núcleo; Python 3.10+ para servidores MCP locais
        Dependências: python3 -m pip install -r requirements/runtime.txt
        Tesseract OCR com pacote de idioma portugues
        Poppler (Windows: extrair para ~/poppler/)

      Proximo passo: capture a sessao do PJE com /capturar-sessao-pje
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      ```
    </acao>
  </fase>

</fases_pipeline>

<resumo_arquitetura>
FLUXO /instalar-superjurista:

  FASE 1: Verificação do Ambiente
  │  Detecta instalação existente
  │  Pergunta ao usuário: Sobrescrever / Mesclar / Cancelar
  │
  ▼
  FASE 2: Cópia do Scaffold
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/commands/    → .claude/commands/
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/agents/      → .claude/agents/
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/skills/      → .claude/skills/
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/mcp-servers/ → .claude/mcp-servers/
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/scripts/     → scripts/ (motor de gate v3.0)
  │  ${CLAUDE_PLUGIN_ROOT}/requirements/         → requirements/
  │  ${CLAUDE_PLUGIN_ROOT}/runtime/              → runtime/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/check_python_contract.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/check_data_hygiene.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/build_claim_matrix.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/build_claim_decisions.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/build_evidence_matrix.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/build_issue_routes.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/build_labor_report.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/classify_labor_documents.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/provider_interfaces.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/pje_session_adapter.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/pje_task_discovery.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/sanitize_pje_har.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/schema_validation.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/validate_pje_har_map.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifact_contracts.py → scripts/
  │  ${CLAUDE_PLUGIN_ROOT}/scripts/validate_tribunal_profile.py → scripts/
  │  + registro dos 5 MCPs no .mcp.json da raiz (caminho absoluto, merge idempotente)
  │
  ▼
  FASE 3: Arquivos Raiz
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/project-claude.md   → ./CLAUDE.md
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/project-readme.md   → ./README.md
  │  ${CLAUDE_PLUGIN_ROOT}/scaffold/project-gitignore   → ./.gitignore
  │
  ▼
  FASE 4: Estrutura de Dados
  │  mkdir -p data/sentenca data/decisao
  │
  ▼
  FASE 5: Resumo
     Exibe componentes instalados e próximos passos
</resumo_arquitetura>
