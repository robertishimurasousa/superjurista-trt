from __future__ import annotations

import copy
import hashlib
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PRECEDENT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "precedent-corpus.v1.schema.json"
)


def source(
    source_id,
    *,
    origin="TRT12",
    source_type="jurisprudence",
    reference=None,
    status="current",
    legal_question=None,
    holding=None,
    excerpt=None,
    url=None,
):
    reference = reference or f"Reference {source_id}"
    legal_question = legal_question or f"Question for {source_id}."
    holding = holding or f"Holding for {source_id}."
    excerpt = excerpt or f"{legal_question} {holding}"
    return {
        "source_id": source_id,
        "origin": origin,
        "type": source_type,
        "reference": reference,
        "status": status,
        "status_notes": [f"Status evidence for {source_id}."],
        "binding_scope": "trt12_regional_jurisdiction",
        "legal_question": legal_question,
        "holding": holding,
        "verbatim_excerpt": excerpt,
        "official_url": url or f"https://example.test/{source_id}",
        "retrieved_at": "2026-09-21T23:00:00Z",
    }


def corpus(*sources):
    return {"schema_version": 1, "sources": list(sources)}


class PrecedentConsolidationTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("consolidate_precedents")
        except ModuleNotFoundError as error:
            self.fail(f"precedent consolidation module is missing: {error}")

    def test_orders_sources_by_legal_hierarchy_then_stable_identifier(self) -> None:
        module = self.api()
        inputs = (
            corpus(
                source("TRT12J-001", source_type="jurisprudence"),
                source("TRT12I-001", source_type="orientation"),
            ),
            corpus(
                source("TSTQ-001", origin="TST", source_type="qualified_precedent"),
                source("TRT12B-001", source_type="binding_precedent"),
            ),
        )

        result = module.consolidate_precedent_corpora(inputs)

        self.assertEqual(
            [item["source_id"] for item in result.corpus["sources"]],
            ["TRT12B-001", "TSTQ-001", "TRT12I-001", "TRT12J-001"],
        )

    def test_exact_repeated_source_is_deduplicated(self) -> None:
        module = self.api()
        repeated = source("TRT12B-021", source_type="binding_precedent")

        result = module.consolidate_precedent_corpora(
            (corpus(repeated), corpus(copy.deepcopy(repeated)))
        )

        self.assertEqual(len(result.corpus["sources"]), 1)
        self.assertEqual(result.duplicate_aliases, ())
        self.assertEqual(len(result.citation_custody), 1)

    def test_repeated_source_id_with_changed_quote_fails_closed(self) -> None:
        module = self.api()
        first = source("TRT12B-021", source_type="binding_precedent")
        changed = copy.deepcopy(first)
        changed["holding"] = "A different holding."
        changed["verbatim_excerpt"] = f"{changed['legal_question']} A different holding."

        with self.assertRaisesRegex(module.PrecedentConsolidationError, "source_id"):
            module.consolidate_precedent_corpora((corpus(first), corpus(changed)))

    def test_equivalent_logical_sources_choose_highest_hierarchy_and_keep_alias_custody(self) -> None:
        module = self.api()
        shared = {
            "origin": "TST",
            "reference": "RR - 0000001-00.2025.5.12.0001",
            "legal_question": "Is the allowance due?",
            "holding": "The allowance is due.",
            "excerpt": "Is the allowance due? The allowance is due.",
        }
        lower = source(
            "TSTJ-101",
            source_type="jurisprudence",
            url="https://example.test/lower",
            **shared,
        )
        higher = source(
            "TSTQ-202",
            source_type="qualified_precedent",
            url="https://example.test/higher",
            **shared,
        )

        result = module.consolidate_precedent_corpora(
            (corpus(lower), corpus(higher))
        )

        self.assertEqual(len(result.corpus["sources"]), 1)
        self.assertEqual(result.corpus["sources"][0]["source_id"], "TSTQ-202")
        self.assertEqual(
            result.duplicate_aliases[0],
            module.DuplicateAlias(
                canonical_source_id="TSTQ-202",
                duplicate_source_id="TSTJ-101",
            ),
        )
        self.assertEqual(
            {item.source_id for item in result.citation_custody},
            {"TSTJ-101", "TSTQ-202"},
        )

    def test_explicit_status_disagreement_is_preserved_as_conflicting(self) -> None:
        module = self.api()
        common = {
            "reference": "TRT12 IRDR theme 23",
            "source_type": "binding_precedent",
            "legal_question": "Does transport generate moral damages?",
            "holding": "Transport alone does not generate moral damages.",
            "excerpt": (
                "Does transport generate moral damages? "
                "Transport alone does not generate moral damages."
            ),
        }
        current = source("TRT12B-023", status="current", **common)
        cancelled = source("TRT12C-023", status="cancelled", **common)

        result = module.consolidate_precedent_corpora(
            (corpus(current), corpus(cancelled))
        )

        merged = result.corpus["sources"][0]
        self.assertEqual(merged["status"], "conflicting")
        self.assertIn(
            "Consolidation conflict: explicit statuses cancelled, current.",
            merged["status_notes"],
        )
        self.assertEqual(
            result.status_conflicts[0].source_statuses,
            (("TRT12B-023", "current"), ("TRT12C-023", "cancelled")),
        )

    def test_unknown_status_does_not_override_an_explicit_status(self) -> None:
        module = self.api()
        common = {
            "reference": "TRT12 IRDR theme 21",
            "source_type": "binding_precedent",
            "legal_question": "Is the schedule valid?",
            "holding": "The schedule is invalid.",
            "excerpt": "Is the schedule valid? The schedule is invalid.",
        }
        unknown = source("TRT12U-021", status="unknown", **common)
        current = source("TRT12B-021", status="current", **common)

        result = module.consolidate_precedent_corpora(
            (corpus(unknown), corpus(current))
        )

        self.assertEqual(result.corpus["sources"][0]["status"], "current")
        self.assertEqual(result.status_conflicts, ())

    def test_holding_and_question_must_remain_inside_verbatim_excerpt(self) -> None:
        module = self.api()
        missing_holding = source(
            "TRT12J-001",
            holding="The actual holding.",
            excerpt="Question for TRT12J-001. Different text.",
        )

        with self.assertRaisesRegex(module.PrecedentConsolidationError, "custody"):
            module.consolidate_precedent_corpora((corpus(missing_holding),))

    def test_citation_custody_uses_exact_excerpt_digest_and_official_location(self) -> None:
        module = self.api()
        item = source(
            "TRT12B-021",
            source_type="binding_precedent",
            excerpt="Question for TRT12B-021. Holding for TRT12B-021.",
            url="https://portal.trt12.jus.br/teses-juridicas",
        )

        result = module.consolidate_precedent_corpora((corpus(item),))
        custody = result.citation_custody[0]

        self.assertEqual(custody.source_id, "TRT12B-021")
        self.assertEqual(custody.official_url, item["official_url"])
        self.assertEqual(
            custody.verbatim_sha256,
            hashlib.sha256(item["verbatim_excerpt"].encode("utf-8")).hexdigest(),
        )

    def test_sidecar_report_serializes_custody_and_merge_decisions(self) -> None:
        module = self.api()
        common = {
            "reference": "TRT12 IRDR theme 21",
            "source_type": "binding_precedent",
            "legal_question": "Is the schedule valid?",
            "holding": "The schedule is invalid.",
            "excerpt": "Is the schedule valid? The schedule is invalid.",
        }
        result = module.consolidate_precedent_corpora(
            (
                corpus(source("TRT12B-021", status="current", **common)),
                corpus(source("TRT12C-021", status="cancelled", **common)),
            )
        )

        report = module.build_consolidation_report(result)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(len(report["citation_custody"]), 2)
        self.assertEqual(report["duplicate_aliases"][0]["duplicate_source_id"], "TRT12C-021")
        self.assertEqual(
            report["status_conflicts"][0]["source_statuses"],
            [
                {"source_id": "TRT12B-021", "status": "current"},
                {"source_id": "TRT12C-021", "status": "cancelled"},
            ],
        )

    def test_invalid_input_contract_is_rejected_before_consolidation(self) -> None:
        module = self.api()
        invalid = corpus(source("TRT12B-021"))
        invalid["sources"][0]["unexpected"] = True

        with self.assertRaisesRegex(module.PrecedentConsolidationError, "contract"):
            module.consolidate_precedent_corpora((invalid,))

    def test_result_remains_a_schema_valid_precedent_corpus(self) -> None:
        module = self.api()
        schema_api = importlib.import_module("schema_validation")
        result = module.consolidate_precedent_corpora(
            (
                corpus(source("TRT12B-021", source_type="binding_precedent")),
                corpus(source("TSTQ-101", origin="TST", source_type="qualified_precedent")),
            )
        )
        schema = schema_api.load_json(PRECEDENT_SCHEMA, "precedent corpus schema")

        self.assertEqual(
            schema_api.validate_schema_value(result.corpus, schema),
            [],
        )


if __name__ == "__main__":
    unittest.main()
