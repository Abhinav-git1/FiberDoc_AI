"""Run the evaluation set through the REAL pipeline (parse -> embed -> LangGraph) and score it.

    python -m evals.run_eval                  # all cases
    python -m evals.run_eval --only clean_pdf all_defects_pdf
    python -m evals.run_eval --fail-under 0.9 # exit 1 if accuracy is below 90%

Needs the database running and GEMINI_API_KEY set. Each case runs in a throwaway project that is deleted afterwards.
"""
import argparse
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.api.projects import _process
from app.db.models import Chunk, Document, Finding, Project
from app.db.session import SessionLocal, init_db
from app.services.retrieval import embed_rules
from app.workflow.seed_rules import seed
from evals.cases import CASES, Case

RESULTS_DIR = Path(__file__).parent / "results"


def build_file(case: Case, folder: Path) -> Path:
    path = folder / f"{case.id}.{case.kind}"
    if case.kind == "pdf":
        import pymupdf

        doc = pymupdf.open()
        for text in case.pages:
            doc.new_page().insert_textbox(pymupdf.Rect(54, 54, 540, 780), text, fontsize=11)
        doc.save(path)
    elif case.kind == "docx":
        from docx import Document as Docx

        d = Docx()
        for para in "\n\n".join(case.pages).split("\n\n"):
            d.add_paragraph(para)
        d.save(path)
    elif case.kind == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Construction plan"
        for para in "\n\n".join(case.pages).split("\n\n"):
            ws.append([para])
        wb.save(path)
    else:
        raise ValueError(case.kind)
    return path


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def run_case(case: Case, folder: Path) -> dict:
    path = build_file(case, folder)
    t0 = time.time()
    with SessionLocal() as db:
        project = Project(name=f"[eval] {case.id}")
        db.add(project)
        db.commit()
        doc = Document(project_id=project.id, name=path.name, status="processing")
        db.add(doc)
        db.commit()
        project_id, doc_id = project.id, doc.id

    _process(doc_id, path)  # the exact code path an upload uses (deletes the temp file when done)

    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        findings = list(db.scalars(select(Finding).where(Finding.document_id == doc_id)))
        doc_text = _norm(" ".join(c.text for c in db.scalars(select(Chunk).where(Chunk.document_id == doc_id))))

        actual: dict[str, str] = {}
        ungrounded = 0
        for f in findings:
            if f.evidence_quote and _norm(f.evidence_quote) not in doc_text:
                ungrounded += 1
            if f.explanation.startswith("Automatic interpretation failed"):
                state = "error"
            elif f.title.endswith("requirement met"):
                state = "ok"
            else:
                state = "flag"
            rank = {"ok": 0, "flag": 1, "error": 2}
            if rank[state] >= rank[actual.get(f.rule_id, "ok")]:
                actual[f.rule_id] = state
        checks = [(r, "flag", actual.get(r, "ok")) for r in case.flag] + [(r, "ok", actual.get(r, "ok")) for r in case.ok]
        result = dict(
            case=case.id, kind=case.kind, note=case.note, seconds=round(time.time() - t0, 1),
            status=doc.status, error=doc.error, doc_type=doc.doc_type, doc_type_ok=doc.doc_type == case.doc_type,
            ungrounded_quotes=ungrounded,
            checks=[dict(rule=r, expected=e, actual=a, correct=(e == a)) for r, e, a in checks],
        )
        # clean up the throwaway project (findings are not cascaded from documents, so delete them first)
        for f in findings:
            db.delete(f)
        db.delete(db.get(Project, project_id))
        db.commit()
    return result


def summarize(results: list[dict]) -> dict:
    checks = [c for r in results for c in r["checks"]]
    n = len(checks)
    tp = sum(1 for c in checks if c["expected"] == "flag" and c["actual"] == "flag")
    fn = sum(1 for c in checks if c["expected"] == "flag" and c["actual"] == "ok")
    fp = sum(1 for c in checks if c["expected"] == "ok" and c["actual"] == "flag")
    tn = sum(1 for c in checks if c["expected"] == "ok" and c["actual"] == "ok")
    inconclusive = sum(1 for c in checks if c["actual"] == "error")
    return dict(
        documents=len(results), checks=n, correct=sum(c["correct"] for c in checks),
        accuracy=round(sum(c["correct"] for c in checks) / n, 3) if n else 0.0,
        recall=round(tp / (tp + fn), 3) if tp + fn else None,
        precision=round(tp / (tp + fp), 3) if tp + fp else None,
        true_pos=tp, false_neg=fn, false_pos=fp, true_neg=tn, inconclusive=inconclusive,
        doc_type_accuracy=round(sum(r["doc_type_ok"] for r in results) / len(results), 3) if results else 0.0,
        ungrounded_quotes=sum(r["ungrounded_quotes"] for r in results),
        failed_documents=[r["case"] for r in results if r["status"] != "awaiting_review"],
    )


def markdown(results: list[dict], s: dict, when: str) -> str:
    lines = [
        "# FiberDoc AI - evaluation results", "", f"Run: {when}", "",
        "| Metric | Value |", "|---|---|",
        f"| Documents | {s['documents']} |", f"| Rule checks | {s['checks']} |",
        f"| **Accuracy** | **{s['accuracy']:.0%}** ({s['correct']}/{s['checks']}) |",
        f"| Recall (planted defects found) | {s['recall'] if s['recall'] is None else format(s['recall'], '.0%')} |",
        f"| Precision (flags that were real) | {s['precision'] if s['precision'] is None else format(s['precision'], '.0%')} |",
        f"| False positives / false negatives | {s['false_pos']} / {s['false_neg']} |",
        f"| Inconclusive (LLM error) | {s['inconclusive']} |",
        f"| Document-type accuracy | {s['doc_type_accuracy']:.0%} |",
        f"| Ungrounded evidence quotes | {s['ungrounded_quotes']} |", "",
        "## Per case", "", "| Case | Type | Result | Wrong checks | Seconds |", "|---|---|---|---|---|",
    ]
    for r in results:
        wrong = ", ".join(f"{c['rule']} (expected {c['expected']}, got {c['actual']})" for c in r["checks"] if not c["correct"])
        ok = all(c["correct"] for c in r["checks"]) and r["status"] == "awaiting_review"
        lines.append(f"| {r['case']} | {r['kind']} | {'PASS' if ok else 'FAIL'} | {wrong or '-'} | {r['seconds']} |")
    lines += ["", "Synthetic documents and demo rules only. Semantic (LLM) rules can vary between runs."]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="case ids to run")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--fail-under", type=float, default=None, help="exit 1 if accuracy is below this (0-1)")
    args = ap.parse_args()

    init_db()
    with SessionLocal() as db:
        seed(db)
        embed_rules(db)

    cases = [c for c in CASES if not args.only or c.id in args.only]
    results: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, c, Path(tmp)): c for c in cases}
        for fut, case in futures.items():
            try:
                r = fut.result()
            except Exception as e:  # a crashed case must show up as a failure, not vanish
                r = dict(case=case.id, kind=case.kind, note=case.note, seconds=0, status="crashed", error=str(e), doc_type="?",
                         doc_type_ok=False, ungrounded_quotes=0,
                         checks=[dict(rule=x, expected=("flag" if x in case.flag else "ok"), actual="error", correct=False)
                                 for x in case.flag + case.ok])
            results.append(r)
            wrong = [c["rule"] for c in r["checks"] if not c["correct"]]
            print(f"{'PASS' if not wrong and r['status'] == 'awaiting_review' else 'FAIL'}  {r['case']:<22} {r['seconds']:>5}s  {wrong or ''}", flush=True)

    s = summarize(results)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "latest.json").write_text(json.dumps(dict(run=when, summary=s, results=results), indent=2))
    (RESULTS_DIR / "latest.md").write_text(markdown(results, s, when), encoding="utf-8")
    print("\n" + json.dumps(s, indent=2))
    print(f"\nWrote {RESULTS_DIR / 'latest.md'}")
    return 1 if args.fail_under is not None and s["accuracy"] < args.fail_under else 0


if __name__ == "__main__":
    raise SystemExit(main())
