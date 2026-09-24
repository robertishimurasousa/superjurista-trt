#!/usr/bin/env python3
"""Build the reproducible file-level reuse ledger for the existing fork."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


COMPONENT_GLOBS = (
    "agents/**/*.md",
    "commands/*.md",
    "skills/*/SKILL.md",
    "scaffold/agents/**/*.md",
    "scaffold/commands/*.md",
    "scaffold/skills/*/SKILL.md",
    "scaffold/scripts/*.py",
    "scaffold/mcp-servers/*/server.py",
)


def discover_components(root: Path) -> list[Path]:
    paths = {path for pattern in COMPONENT_GLOBS for path in root.glob(pattern) if path.is_file()}
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def component_kind(relative: str) -> str:
    if relative.startswith("scaffold/mcp-servers/"):
        return "provider"
    if "/scripts/" in relative:
        return "script"
    if "/agents/" in relative or relative.startswith("agents/"):
        return "agent"
    if "/commands/" in relative or relative.startswith("commands/"):
        return "command"
    if "/skills/" in relative or relative.startswith("skills/"):
        return "skill"
    raise ValueError(f"unclassified component kind: {relative}")


def classify(relative: str) -> tuple[str, str]:
    if relative == "scaffold/scripts/verificar_pipeline.py":
        return "preserve", "O motor determinístico de verificações, independente do tribunal, é a base compartilhada de execução."
    if relative.startswith("scaffold/scripts/"):
        return "adapt", "O script determinístico pode ser reutilizado após revisão de portabilidade e dos contratos trabalhistas."
    if relative.startswith("scaffold/agents/lista-trf/"):
        return "retire", "O tratamento de listas de julgamento dos TRFs não integra o fluxo executável do primeiro grau do TRT12."
    if relative.startswith("scaffold/agents/pesquisa/pesquisador-") and any(
        source in relative for source in ("cjf", "julia", "stj", "tnu")
    ):
        return "retire", "A pesquisa da Justiça Federal é substituída por fontes de autoridade do TST e do TRT12 para a Justiça do Trabalho."
    if relative in {
        "scaffold/agents/analise/analisador-marmelstein.md",
        "scaffold/agents/analise/fundamentador-marmelstein.md",
        "scaffold/agents/revisao/verificador-calculos.md",
        "scaffold/agents/revisao/verificador-honorarios.md",
        "scaffold/agents/revisao/verificador-remessa.md",
    }:
        return "replace", "Premissas federais sobre mérito ou revisão exigem contrato específico da Justiça do Trabalho."
    if relative.startswith("scaffold/mcp-servers/"):
        if "/bnp-api/" in relative:
            return "adapt", "O BNP continua aplicável após adaptação da política de autoridades e da interface de execução."
        return "retire", "O provedor não integra o conjunto aprovado de fontes para o primeiro grau do TRT12."
    if relative == "scaffold/skills/jurisprudencia-eleitoral/SKILL.md":
        return "retire", "A jurisprudência eleitoral está fora do escopo do primeiro grau do TRT12."
    if relative == "scaffold/skills/fork-terminal/SKILL.md":
        return "replace", "A bifurcação de terminais do Claude é substituída por despacho independente do ambiente de execução."
    if relative.startswith(("agents/", "commands/", "skills/")):
        return "adapt", "As metaferramentas são úteis, mas ainda emitem caminhos ou ferramentas específicos do Claude."
    if relative.startswith("scaffold/"):
        return "adapt", "A capacidade possui comportamento reutilizável, mas exige adaptação ao domínio trabalhista ou ao ambiente de execução."
    raise ValueError(f"unclassified component: {relative}")


def runtime_dependencies(text: str) -> list[str]:
    dependencies = []
    checks = (
        ("claude_browser_mcp", "mcp__claude-in-chrome__" in text),
        ("claude_frontmatter", "allowed-tools:" in text),
        ("claude_paths", ".claude/" in text or "CLAUDE_PLUGIN_ROOT" in text),
        ("claude_progress_tool", "TodoWrite" in text),
        ("claude_task_tool", bool(re.search(r"\bTask(?: tool)?\b", text))),
    )
    for name, present in checks:
        if present:
            dependencies.append(name)
    return dependencies


def build_ledger(root: Path) -> dict:
    components = []
    unclassified = []
    for path in discover_components(root):
        relative = path.relative_to(root).as_posix()
        try:
            disposition, rationale = classify(relative)
            kind = component_kind(relative)
        except ValueError:
            unclassified.append(relative)
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        components.append(
            {
                "path": relative,
                "kind": kind,
                "disposition": disposition,
                "rationale": rationale,
                "runtime_dependencies": runtime_dependencies(text),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    counts = Counter(item["disposition"] for item in components)
    return {
        "schema_version": 1,
        "locale": "pt-BR",
        "scope": list(COMPONENT_GLOBS),
        "component_count": len(components),
        "unclassified_count": len(unclassified),
        "unclassified": unclassified,
        "summary": {name: counts.get(name, 0) for name in ("preserve", "adapt", "replace", "retire")},
        "components": components,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SuperJurista fork reuse ledger.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    ledger = build_ledger(root)
    if ledger["unclassified_count"]:
        for path in ledger["unclassified"]:
            print(f"[UNCLASSIFIED] {path}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[OK] reuse ledger: {ledger['component_count']} components, "
        f"{ledger['unclassified_count']} unclassified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
