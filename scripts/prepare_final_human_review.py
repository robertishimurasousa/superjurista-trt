#!/usr/bin/env python3
"""Prepara roteiro protegido para revisão humana da minuta consolidada."""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
from pathlib import Path

from run_draft_judgment_stage import _write_once
from schema_validation import load_json
from trt12_initial_gate import TRT12_NUMBER
from trt12_merge_gate import make_merge_gate


ROOT = Path(__file__).resolve().parents[1]
PACKET_NAME = "final-human-review.md"
SOURCE_NAMES = (
    "case-context.json",
    "document-index.json",
    "source-manifest.json",
    "claim-matrix.json",
    "evidence-matrix.json",
    "precedent-corpus.json",
    "evidence-review.json",
    "calculation-review.json",
    "claim-analysis.json",
    "disposition-matrix.json",
    "judgment-draft.md",
)


class FinalHumanReviewPacketError(ValueError):
    """Indica que o roteiro não pode ser preparado com segurança."""


def _render_packet(hashes: dict[str, str], claims: dict, analysis: dict, dispositions: dict) -> str:
    """Expõe somente IDs e custódia; todas as conclusões ficam em branco."""
    analyses = {item["claim_id"]: item for item in analysis["analyses"]}
    dispositive = {item["claim_id"]: item for item in dispositions["items"]}
    lines = [
        "# Roteiro protegido de revisão jurídica final",
        "",
        "Este arquivo não constitui aprovação jurídica, decisão judicial ou autorização",
        "para assinatura, publicação ou outro ato externo. A minuta é consultiva.",
        "Antes de usá-lo, congele a revisão cega dos pedidos sem consultar as saídas",
        "do sistema. Se isso não ocorreu, interrompa esta etapa.",
        "",
        "Revisor(a): [preencher]",
        "Data e hora: [preencher]",
        "PDF original e custódia consultados: [preencher]",
        "",
        "## Custódia das saídas apresentadas",
        "",
        "Compare os resumos abaixo com os arquivos antes e depois da revisão.",
        "O PDF original e seus documentos devem ser conferidos separadamente.",
        "",
        "| Arquivo | SHA-256 |",
        "|---|---|",
    ]
    lines.extend(f"| `{name}` | `{digest}` |" for name, digest in hashes.items())
    lines.extend(("", "## Conferência por pedido", ""))
    for claim in claims["claims"]:
        claim_id = claim["claim_id"]
        item = analyses[claim_id]
        decision = dispositive[claim_id]
        lines.extend((
            f"### {claim_id}",
            "",
            f"Análise: `{item['analysis_id']}`. Dispositivo: `{decision['disposition_id']}`.",
            f"Resultado proposto pelo sistema: `{item['proposed_outcome']}`; não aprovado.",
            "IDs de evidência: " + (", ".join(item["evidence_ids"]) or "nenhum") + ".",
            "IDs de fontes jurídicas: "
            + (", ".join(item["precedent_source_ids"]) or "nenhum") + ".",
            "",
            "- [ ] Comparei pedido, subitens e defesas com o PDF original e o inventário cego.",
            "- [ ] Conferi páginas, contexto visual, contradições e limites das provas.",
            "- [ ] Conferi vigência, âmbito e trecho literal de cada fonte jurídica citada.",
            "- [ ] Conferi fatos, norma, fundamentação, cálculos e resultado proposto.",
            "- [ ] Comparei o dispositivo e a minuta com o pedido e as conclusões revisadas.",
            "- [ ] Registrei omissões, divergências, abstenções e correções necessárias.",
            "Conclusão jurídica do revisor: [preencher; não inferir do resultado proposto]",
            "Justificativa e correções: [preencher]",
            "",
        ))
    lines.extend((
        "## Encerramento",
        "",
        "- [ ] Todos os pedidos e subitens foram conferidos por revisor qualificado.",
        "- [ ] Revisei as citações, os cálculos e a congruência da minuta integral.",
        "- [ ] Registrei identidade, data, divergências e versão dos arquivos examinados.",
        "- [ ] Entendi que este roteiro não alimenta automaticamente o controle final.",
        "",
        "A revisão preenchida deve permanecer em local protegido e ser verificada",
        "por procedimento próprio antes de qualquer aceitação técnica posterior.",
        "",
    ))
    return "\n".join(lines)


def prepare_final_human_review(workspace: Path) -> Path:
    """Confere a minuta e grava um roteiro privado sem conclusões automáticas."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise FinalHumanReviewPacketError("espaço do processo inválido")
    target = workspace.resolve()
    if target == ROOT or target.is_relative_to(ROOT):
        raise FinalHumanReviewPacketError("o roteiro deve ficar fora do repositório")
    if stat.S_IMODE(target.stat().st_mode) & 0o077:
        raise FinalHumanReviewPacketError("espaço do processo deve ser privado")
    output = target / PACKET_NAME
    if output.exists() or output.is_symlink():
        raise FinalHumanReviewPacketError("roteiro já existe e não será sobrescrito")
    try:
        context_path = target / "case-context.json"
        if context_path.is_symlink() or not context_path.is_file():
            raise FinalHumanReviewPacketError("contexto ausente ou vínculo simbólico")
        context = load_json(context_path, "contexto do processo")
        case_number = context.get("case_number")
        if not isinstance(case_number, str) or TRT12_NUMBER.fullmatch(case_number) is None:
            raise FinalHumanReviewPacketError("número do processo TRT12 inválido")
        merged_name = f"{case_number}-labor-judgment.md"
        names = (*SOURCE_NAMES, merged_name)
        hashes = {}
        for name in names:
            source = target / name
            if source.is_symlink() or not source.is_file():
                raise FinalHumanReviewPacketError("fonte ausente ou vínculo simbólico")
            hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        if not make_merge_gate(target)(
            {"id": "merge-judgment", "gate": "deterministic-merge"},
            ((target / merged_name).resolve(),),
        ):
            raise FinalHumanReviewPacketError("controle da minuta consolidada reprovado")
        claims = load_json(target / "claim-matrix.json", "matriz de pedidos")
        analysis = load_json(target / "claim-analysis.json", "análise dos pedidos")
        dispositions = load_json(target / "disposition-matrix.json", "dispositivo")
        content = _render_packet(hashes, claims, analysis, dispositions).encode("utf-8")
        _write_once(output, content)
        return output
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        if isinstance(error, FinalHumanReviewPacketError):
            raise
        raise FinalHumanReviewPacketError("preparo do roteiro de revisão recusado") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara roteiro protegido para revisão jurídica da minuta."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare_final_human_review(args.workspace)
    except FinalHumanReviewPacketError as error:
        print(f"[ERRO] Roteiro de revisão final: {error}", file=sys.stderr)
        return 2
    print("[OK] Roteiro privado criado; nenhuma conclusão jurídica registrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
