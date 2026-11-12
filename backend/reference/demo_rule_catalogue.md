# FiberDoc Demo Rule Catalogue

> **NON-AUTHORITATIVE DEMO CONTENT.** Every requirement, limit, rule ID and name in this document was invented to
> demonstrate FiberDoc AI. None of it is an official telecom, utility, safety or regulatory standard. The jurisdiction
> and standard family below are placeholders. Do not use this catalogue for real engineering or compliance decisions.

This file is the source of truth for the rule set. `app/workflow/seed_rules.py` parses it, and the app loads the
rules into the database on startup. Each `###` heading is one rule: the rule-sized unit that is embedded and retrieved.

How a rule is written:

- `severity`: high | medium | low
- `applies_to`: comma-separated document types (construction_plan, design_summary, as_built, permit, test_report), or `all`
- `keywords`: comma-separated words used to boost retrieval
- `check`: how the rule is checked
  - `required_term`: passes if any `pattern` line matches anywhere in the document
  - `numeric_min` / `numeric_max`: the `pattern` captures one number, which is compared with `limit`
  - `consistency`: `pattern_a` and `pattern_b` each capture a number, and the two must be equal
  - `semantic`: interpreted by the LLM over retrieved evidence (each one uses a Gemini call per document, so keep these few)
- `pattern`, `pattern_a`, `pattern_b`: case-insensitive Python regular expressions, written raw inside backticks
- `what`: a short name for the evidence, used in finding explanations
- `example_pass` / `example_fail`: short texts that must pass and fail the check. The tests run these for every rule.
- The paragraph under the bullets is the requirement text shown to reviewers.

## Catalogue

- source_name: FiberDoc Demo Rule Catalogue (non-authoritative)
- jurisdiction: DEMO-REGION-A
- standard_family: DEMO-STD-1
- version: 0.2
- effective_date: 2026-01-01
- status: approved

## Section: Quality assurance

### QA-014: Splice loss test results missing
- severity: high
- applies_to: construction_plan, test_report, as_built
- keywords: otdr, splice, loss
- check: required_term
- pattern: `otdr`
- pattern: `splice loss`
- what: OTDR / splice-loss results
- example_pass: `OTDR traces recorded for all 12 splices.`
- example_fail: `Splicing will be completed at SP-01 through SP-03.`

Every spliced segment must include OTDR test results with measured loss per splice.

### QA-021: Splice loss above the demo limit
- severity: high
- applies_to: test_report, as_built
- keywords: splice, loss, db
- check: numeric_max
- pattern: `splice loss\D{0,40}?(\d+(?:\.\d+)?)\s*dB`
- limit: 0.15
- unit: dB
- what: splice loss
- example_pass: `Maximum splice loss 0.06 dB across all splices.`
- example_fail: `Maximum splice loss 0.32 dB at SP-07.`

Measured loss for any single fusion splice must not exceed 0.15 dB (demo limit). The highest reported value is checked.

### QA-022: Test wavelength not stated
- severity: medium
- applies_to: test_report, as_built
- keywords: wavelength, nm, otdr
- check: required_term
- pattern: `\b1310\s*nm`
- pattern: `\b1550\s*nm`
- what: test wavelength (1310 / 1550 nm)
- example_pass: `OTDR traces taken at 1310 nm and 1550 nm.`
- example_fail: `OTDR traces recorded for all splices.`

OTDR and loss test results must state the test wavelength. Demo requirement: 1310 nm and/or 1550 nm.

## Section: Design

### DSN-003: Fiber count inconsistent between sections
- severity: high
- applies_to: construction_plan, design_summary
- keywords: fiber, count, schedule
- check: consistency
- pattern_a: `design summary[\s\S]{0,200}?(\d+)-count`
- pattern_b: `cable schedule[\s\S]{0,200}?(\d+)-count`
- what: fiber count
- example_pass: `Design summary: 48-count cable. Cable schedule: 48-count cable on all segments.`
- example_fail: `Design summary: 48-count cable. Cable schedule: 96-count cable on all segments.`

Fiber count stated in the design summary must match the cable schedule.

### DSN-011: Minimum bend radius not stated
- severity: medium
- applies_to: design_summary, construction_plan
- keywords: bend, radius
- check: required_term
- pattern: `bend radius`
- what: minimum bend radius
- example_pass: `Minimum bend radius: 20x cable diameter during installation.`
- example_fail: `Cable installed in 2-inch HDPE conduit.`

Design must state the minimum bend radius for installed cable (>= 15x cable diameter).

### DSN-014: Fiber type not specified
- severity: medium
- applies_to: design_summary, construction_plan
- keywords: single-mode, fiber, type, cable
- check: required_term
- pattern: `single[- ]mode`
- pattern: `\bG\.65\d`
- pattern: `\bOS2\b`
- what: fiber type (for example single-mode)
- example_pass: `144-count single-mode cable along Route B.`
- example_fail: `144-count cable along Route B.`

The design must name the fiber type, for example single-mode (demo examples of acceptable wording: single-mode, G.652, OS2).

### DSN-018: Slack loops or spare capacity not shown
- severity: low
- applies_to: design_summary, construction_plan, as_built
- keywords: slack, loop, spare, capacity
- check: required_term
- pattern: `slack (?:loop|storage|coil)`
- pattern: `spare (?:fibers?|capacity|conduit)`
- what: slack loops or spare capacity
- example_pass: `A 30 m slack loop is stored at each handhole.`
- example_fail: `Handholes every 300 m along the route.`

Designs must show slack loops (demo: at each handhole and splice point) or state the spare fiber or conduit capacity.

## Section: Construction

### CON-007: Conduit burial depth may be below requirement
- severity: medium
- applies_to: construction_plan, design_summary, as_built
- keywords: conduit, depth, trench, burial
- check: numeric_min
- pattern: `(\d+(?:\.\d+)?)\s*(?:in\.|inch(?:es)?|")\s*(?:deep|depth|below grade)?`
- limit: 36
- unit: in
- what: burial depth
- example_pass: `Conduit buried at 42 in. below grade.`
- example_fail: `Conduit buried at 30 inches below grade.`

Underground conduit must be buried at least 36 inches below grade unless a waiver is attached.

### CON-012: Handhole spacing above the demo limit
- severity: medium
- applies_to: construction_plan, design_summary, as_built
- keywords: handhole, spacing, interval
- check: numeric_max
- pattern: `handholes?\D{0,40}?every\s*(\d+(?:\.\d+)?)\s*m\b`
- limit: 300
- unit: m
- what: handhole spacing
- example_pass: `Handholes are placed every 150 m.`
- example_fail: `Handholes are placed every 450 m.`

Handholes must be placed at intervals of no more than 300 m (demo limit) so cable can be pulled and accessed.

### CON-015: Warning tape or tracer wire not specified
- severity: medium
- applies_to: construction_plan, as_built
- keywords: warning, tape, tracer, wire, locate
- check: required_term
- pattern: `warning tape`
- pattern: `marker tape`
- pattern: `tracer wire`
- pattern: `locate wire`
- what: warning tape or tracer wire
- example_pass: `Tracer wire placed with the conduit and warning tape above it.`
- example_fail: `Conduit placed in the trench and backfilled.`

Underground conduit must have warning tape above it and a tracer wire so the route can be located later.

### CON-019: Utility locate before excavation not referenced
- severity: high
- applies_to: construction_plan
- keywords: locate, utility, excavation, trench
- check: required_term
- pattern: `utility locate`
- pattern: `locate (?:ticket|request)`
- pattern: `one-call`
- what: utility locate before excavation
- example_pass: `Utility locate ticket DEMO-LT-0091 obtained before trenching.`
- example_fail: `Trench to be excavated along the east shoulder.`

Plans that include excavation must reference a utility locate (demo: a locate ticket obtained before digging starts).

## Section: Permits

### PRM-002: Permit referenced but not attached
- severity: low
- applies_to: all
- keywords: permit
- check: semantic
- example_pass: `Right-of-way approved under permit no. DEMO-PRM-0042 (attached as Appendix B).`
- example_fail: `Right-of-way approved under city permit (copy on file).`

Permits cited in the document must be attached or referenced by permit number.

### PRM-005: Traffic control plan not referenced
- severity: medium
- applies_to: construction_plan, permit
- keywords: traffic, control, roadway
- check: required_term
- pattern: `traffic control`
- what: traffic control plan
- example_pass: `Traffic control plan TCP-3 applies to all roadway work.`
- example_fail: `Work takes place along the roadway shoulder.`

Construction plans and permits for work in or next to a roadway must include or reference a traffic control plan.

### PRM-008: Permit validity dates missing
- severity: low
- applies_to: permit
- keywords: permit, expiry, valid, date
- check: required_term
- pattern: `expir(?:es|y|ation)`
- pattern: `valid (?:until|through|from)`
- what: permit validity or expiry date
- example_pass: `Permit valid until 2027-03-31.`
- example_fail: `Permit no. DEMO-PRM-0042 issued to Demo Fiber Co.`

Permit documents must state when the permit is valid, including its expiry date.

## Section: Labelling

### LBL-001: Cable labelling convention
- severity: low
- applies_to: as_built
- keywords: tag, label
- check: semantic
- example_pass: `Cable tag: DEMO-SITE-01/RT-B/144F.`
- example_fail: `Cables are tagged in the field.`

Cable tags must follow the site-ID/route/fiber-count format.

### LBL-004: Structure identifiers missing
- severity: low
- applies_to: as_built, construction_plan
- keywords: handhole, splice, identifier, id
- check: required_term
- pattern: `\bHH-\d+`
- pattern: `\bMH-\d+`
- pattern: `\bSP-\d+`
- what: handhole / manhole / splice point identifiers
- example_pass: `Splice at SP-03 inside handhole HH-12.`
- example_fail: `Splice inside the handhole near the cabinet.`

Every handhole, manhole and splice point must carry a unique ID (demo format HH-nn, MH-nn, SP-nn) that is used consistently across drawings.

## Section: Safety

### SAF-002: Site safety plan not referenced
- severity: medium
- applies_to: construction_plan
- keywords: safety, hazard, plan
- check: required_term
- pattern: `safety plan`
- pattern: `job hazard analysis`
- pattern: `\bJHA\b`
- what: site safety plan or job hazard analysis
- example_pass: `Crews follow site safety plan SSP-2 and a daily job hazard analysis.`
- example_fail: `Crews start work at 7:00 each day.`

Construction plans must reference a site safety plan or job hazard analysis that covers the work.

## Section: As-built records

### ASB-001: Structure coordinates missing
- severity: medium
- applies_to: as_built
- keywords: gps, coordinates, location
- check: required_term
- pattern: `\bgps\b`
- pattern: `coordinates?`
- pattern: `latitude`
- what: GPS coordinates of placed structures
- example_pass: `HH-01 GPS: 42.3601, -71.0589.`
- example_fail: `HH-01 placed near the cabinet.`

As-built records must give GPS coordinates for every placed handhole, manhole and splice closure.

### ASB-003: Installed cable length missing
- severity: low
- applies_to: as_built
- keywords: length, footage, installed
- check: required_term
- pattern: `installed (?:length|footage)`
- pattern: `as-built (?:length|footage)`
- pattern: `route length`
- what: installed cable length
- example_pass: `Installed length: 1,240 m.`
- example_fail: `Cable installed between HH-01 and HH-14.`

As-built records must state the installed cable length for each segment.

## Section: Splicing

### SPL-002: Splice plan missing
- severity: medium
- applies_to: construction_plan
- keywords: splice, plan, matrix
- check: required_term
- pattern: `splice (?:plan|matrix|diagram|schedule)`
- what: splice plan or splice matrix
- example_pass: `See the splice matrix in Appendix C.`
- example_fail: `Splicing at SP-01 through SP-03.`

Construction plans with splicing must include or reference a splice plan or splice matrix showing which fibers are joined.
