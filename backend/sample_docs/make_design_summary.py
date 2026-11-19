"""Generate a synthetic fiber DESIGN SUMMARY (demo data only) for checking the classifier the other way round.

The 2026-11-19 classifier fix weights title hits 5x so that a construction plan with "Design summary" headings is
classified as a construction plan. This document is the opposite trap: a design summary whose text mentions the
construction plan, the scope of work and trenching in passing. It must still be classified as design_summary.

Run from backend/:  python sample_docs/make_design_summary.py
"""
import sys

import fitz

PAGES = [
    "METRO RING NORTH - SEGMENT 5 (SYNTHETIC DEMO DOCUMENT)\n\nDesign Summary\n\nPrepared by: Demo Engineering Co.\n"
    "Date: 2026-11-19\n\n1. Design basis\nThe design basis is a 96-count single-mode ring between cabinets DEMO-CAB-05 "
    "and DEMO-CAB-09, sized for 20 years of growth at 70% fiber utilisation.\n\n2. Fiber counts\nFeeder: 96-count "
    "G.652.D loose-tube cable. Distribution: 48-count cable to each of 6 splitter cabinets.",
    "3. Cable schedule\nSegment 5A: 96-count cable, 1.4 km, underground.\nSegment 5B: 96-count cable, 0.9 km, aerial.\n"
    "Segment 5C: 48-count cable, 0.6 km, underground.\n\n4. Splitter and splice architecture\nCentralised 1:32 "
    "splitting in each cabinet. Splice closures at every branch point; minimum bend radius 20x cable diameter.",
    "5. Notes for the next phase\nThe construction plan, including the scope of work, trenching methods, traffic "
    "control and utility locates, will be issued separately once this design is approved.\n\n"
    "6. Approval\nDesign review: pending.",
]
out = sys.argv[1] if len(sys.argv) > 1 else "sample_docs/MRN-S8_design_summary.pdf"
doc = fitz.open()
for text in PAGES:
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, 540, 780), text, fontsize=11)
doc.save(out)
print("wrote", out)
