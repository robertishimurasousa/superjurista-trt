"""Monta despachos Codex com as superfícies configuráveis desabilitadas."""

from __future__ import annotations

from typing import Optional


def codex_restricted_command(model_id: Optional[str] = None) -> list[str]:
    """Desabilita superfícies configuráveis de execução, navegação e aplicativos."""
    command = [
        "codex", "--ask-for-approval", "never", "exec",
        "--sandbox", "read-only", "--ephemeral", "--ignore-user-config",
        "--strict-config", "--disable", "shell_tool", "--disable", "multi_agent",
        "--disable", "apps", "--disable", "browser_use",
        "--disable", "browser_use_external",
        "--disable", "browser_use_full_cdp_access",
        "--disable", "computer_use", "--disable", "code_mode_host",
        "--config", 'web_search="disabled"',
        "--config", "apps._default.enabled=false", "--skip-git-repo-check",
    ]
    if model_id is not None:
        command.extend(("--model", model_id))
    command.append("-")
    return command
