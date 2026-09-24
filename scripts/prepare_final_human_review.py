#!/usr/bin/env python3
"""Prepara roteiro protegido para revisão humana da minuta consolidada."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path

from run_draft_judgment_stage import _write_once
from schema_validation import load_json, validate_schema_value
from trt12_initial_gate import TRT12_NUMBER
from trt12_merge_gate import make_merge_gate


ROOT = Path(__file__).resolve().parents[1]
PACKET_NAME = "final-human-review.md"
REVIEW_NAME = "final-human-review.json"
REVIEW_SCHEMA = ROOT / "runtime/operations/final-human-review.v1.schema.json"
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
        "Revisor(a): [preencher em `final-human-review.json`]",
        "Data e hora: [preencher em `final-human-review.json`]",
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
            "Conclusão jurídica: [preencher em `final-human-review.json`; não inferir]",
            "Justificativa e correções: [preencher em `final-human-review.json`]",
            "",
        ))
    lines.extend((
        "## Encerramento",
        "",
        "- [ ] Todos os pedidos e subitens foram conferidos por revisor qualificado.",
        "- [ ] Revisei as citações, os cálculos e a congruência da minuta integral.",
        "- [ ] Registrei identidade, data, divergências e versão dos arquivos examinados.",
        "- [ ] Registrei as decisões no JSON e executei o validador de revisão.",
        "",
        "O registro preenchido deve permanecer em local protegido. A validação",
        "confere declarações e custódia, mas não autentica o revisor nem aprova a minuta.",
        "",
    ))
    return "\n".join(lines)


def current_review_sources(workspace: Path) -> tuple[Path, dict[str, str], dict, dict, dict]:
    """Revalida o controle herdado e reúne a custódia atual dos arquivos."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise FinalHumanReviewPacketError("espaço do processo inválido")
    target = workspace.resolve()
    if target == ROOT or target.is_relative_to(ROOT):
        raise FinalHumanReviewPacketError("o roteiro deve ficar fora do repositório")
    if stat.S_IMODE(target.stat().st_mode) & 0o077:
        raise FinalHumanReviewPacketError("espaço do processo deve ser privado")
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
        return target, hashes, claims, analysis, dispositions
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        if isinstance(error, FinalHumanReviewPacketError):
            raise
        raise FinalHumanReviewPacketError("preparo do roteiro de revisão recusado") from error


def review_template(hashes: dict[str, str], claims: dict, analysis: dict,
                    dispositions: dict) -> dict:
    """Cria decisões explicitamente pendentes para cada pedido atual."""
    analyses = {item["claim_id"]: item for item in analysis["analyses"]}
    dispositive = {item["claim_id"]: item for item in dispositions["items"]}
    return {
        "schema_version": 1,
        "source_hashes": [
            {"name": name, "sha256": digest} for name, digest in hashes.items()
        ],
        "reviewer_name": "",
        "reviewed_at": "",
        "blind_inventory_frozen": False,
        "original_pdf_checked": False,
        "claims": [
            {
                "claim_id": claim["claim_id"],
                "analysis_id": analyses[claim["claim_id"]]["analysis_id"],
                "disposition_id": dispositive[claim["claim_id"]]["disposition_id"],
                "proposed_outcome": analyses[claim["claim_id"]]["proposed_outcome"],
                "source_checked": False,
                "law_checked": False,
                "draft_checked": False,
                "decision": "pending",
                "reason": "",
            }
            for claim in claims["claims"]
        ],
    }


def prepare_final_human_review(workspace: Path) -> Path:
    """Publica roteiro e registro pendente sem conclusão jurídica automática."""
    target, hashes, claims, analysis, dispositions = current_review_sources(workspace)
    packet = target / PACKET_NAME
    record = target / REVIEW_NAME
    if any(path.exists() or path.is_symlink() for path in (packet, record)):
        raise FinalHumanReviewPacketError("roteiro ou revisão já existe; arquivos preservados")
    try:
        template = review_template(hashes, claims, analysis, dispositions)
        if validate_schema_value(template, load_json(REVIEW_SCHEMA, "esquema da revisão final")):
            raise FinalHumanReviewPacketError("modelo de revisão final inválido")
        packet_bytes = _render_packet(hashes, claims, analysis, dispositions).encode("utf-8")
        record_bytes = (json.dumps(template, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        _write_once(packet, packet_bytes)
        try:
            _write_once(record, record_bytes)
        except Exception:
            packet.unlink(missing_ok=True)
            raise
        return packet
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        if isinstance(error, FinalHumanReviewPacketError):
            raise
        raise FinalHumanReviewPacketError("publicação do roteiro de revisão recusada") from error


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
    print("[OK] Roteiro e registro privado pendente criados; nenhuma conclusão jurídica registrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
