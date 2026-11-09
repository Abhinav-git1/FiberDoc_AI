"""Generate a synthetic fiber construction document with deliberate defects (demo data only).

Expected findings: QA-014 (no OTDR results), DSN-011 (no bend radius),
DSN-003 (144-count vs 96-count), CON-007 (30 in. depth < 36 in.), PRM-002 (permit without number).
"""
import sys
import fitz

PAGES = [
    "METRO RING NORTH - SEGMENT 4 (SYNTHETIC DEMO DOCUMENT)\n\nConstruction Plan\n\nScope of work: install underground conduit and fiber cable along Route A, "
    "including trenching, handhole placement and a splice plan for 24 splice points.\n\nRoute length: 4.2 km.",
    "Design summary: 144-count single-mode cable along Route A.\n\nCable type: G.652.D loose-tube armored.\n\nSplice locations are listed in the splice plan.",
    "Trenching notes\n\nTrench to be excavated to approximately 30 in. along the east shoulder.\n\nHandholes every 300 m.",
    "Permits\n\nPole attachments approved per city permit (copy on file).",
    "Cable schedule\n\nRoute A uses 96-count single-mode cable between handholes HH-01 and HH-14.",
]
out = sys.argv[1] if len(sys.argv) > 1 else "sample_docs/MRN-S4_construction_plan.pdf"
doc = fitz.open()
for text in PAGES:
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, 540, 780), text, fontsize=11)
doc.save(out)
print("wrote", out)
