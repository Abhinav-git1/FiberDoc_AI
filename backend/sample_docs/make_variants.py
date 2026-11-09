"""More synthetic documents for the evaluation set (demo data only). Run from backend/:
    python sample_docs/make_variants.py

MRN-S5_compliant_plan.pdf   construction plan, NO defects: every rule should pass (PRM-002 cites a permit number).
MRN-S6_asbuilt_bad_tags.pdf as-built whose cable tags do NOT follow site-ID/route/fiber-count (LBL-001 should fail).
MRN-S7_asbuilt_good_tags.pdf as-built whose cable tags DO follow the format (LBL-001 should pass).
"""
import fitz

DOCS = {
    "MRN-S5_compliant_plan.pdf": [
        "METRO RING NORTH - SEGMENT 5 (SYNTHETIC DEMO DOCUMENT)\n\nConstruction Plan\n\nScope of work: trenching, conduit and fiber cable along Route B, "
        "including handhole placement and a splice plan for 18 splice points.",
        "Design summary: 96-count single-mode cable along Route B.\n\nMinimum bend radius: 15x cable diameter during installation and after.",
        "Trenching notes\n\nConduit to be buried 42 in. below grade along the east shoulder.",
        "Permits\n\nPole attachments approved under City Permit No. CP-2291 (attached as Appendix C).",
        "Cable schedule\n\nRoute B uses 96-count single-mode cable between handholes HH-21 and HH-30.\n\n"
        "Test results: OTDR traces and measured loss for all 18 splices are attached as Appendix D.",
    ],
    "MRN-S6_asbuilt_bad_tags.pdf": [
        "METRO RING NORTH - SEGMENT 6 AS-BUILT (SYNTHETIC DEMO DOCUMENT)\n\nRecord drawing of installed cable.",
        "Cable labelling\n\nThe cable at HH-03 carries a tag reading 'blue cable'.\nThe cable at HH-07 is tagged 'CBL-7'.\n"
        "Technicians identify the rest by colour and location.",
    ],
    "MRN-S7_asbuilt_good_tags.pdf": [
        "METRO RING NORTH - SEGMENT 7 AS-BUILT (SYNTHETIC DEMO DOCUMENT)\n\nRecord drawing of installed cable.",
        "Cable labelling\n\nAll cables are tagged site-ID/route/fiber-count:\nHH-03/RouteA/96F\nHH-07/RouteA/96F\nHH-14/RouteB/48F",
    ],
}

for name, pages in DOCS.items():
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_textbox(fitz.Rect(54, 54, 540, 780), text, fontsize=11)
    doc.save(f"sample_docs/{name}")
    print("wrote", name)
