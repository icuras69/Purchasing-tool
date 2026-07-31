from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf"
PAGE_WIDTH, PAGE_HEIGHT = A4

NAVY = colors.HexColor("#10243E")
BLUE = colors.HexColor("#1E5A8A")
TEAL = colors.HexColor("#16A6A1")
PALE_TEAL = colors.HexColor("#E8F7F5")
PALE_BLUE = colors.HexColor("#EAF1F8")
PALE_AMBER = colors.HexColor("#FFF4D8")
PALE_RED = colors.HexColor("#FCE8E6")
INK = colors.HexColor("#17212B")
MUTED = colors.HexColor("#5A6978")
LINE = colors.HexColor("#D6DEE6")
WHITE = colors.white


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=33,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=12,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=19,
            textColor=colors.HexColor("#DDEAF6"),
            spaceAfter=8,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#79D8D3"),
        ),
        "h1": ParagraphStyle(
            "Heading1Custom",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=NAVY,
            spaceBefore=2,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "Heading2Custom",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "Heading3Custom",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
            spaceBefore=7,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "BodyCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=INK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "SmallCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "bullet": ParagraphStyle(
            "BulletCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13,
            leftIndent=13,
            firstLineIndent=-9,
            bulletIndent=0,
            textColor=INK,
            spaceAfter=3,
        ),
        "callout": ParagraphStyle(
            "CalloutCustom",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=NAVY,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=WHITE,
            alignment=TA_LEFT,
        ),
        "table_body": ParagraphStyle(
            "TableBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=INK,
        ),
        "status": ParagraphStyle(
            "Status",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
    }


STYLES = styles()


def page_decoration(canvas, doc):
    canvas.saveState()
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
        canvas.setFillColor(TEAL)
        canvas.rect(0, PAGE_HEIGHT - 18 * mm, PAGE_WIDTH, 18 * mm, stroke=0, fill=1)
    else:
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 15 * mm, PAGE_WIDTH - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, "Purchasing Tool - Final Delivery")
        canvas.drawRightString(PAGE_WIDTH - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def paragraph(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullets(items: list[str]) -> list:
    result = []
    for item in items:
        result.append(Paragraph(f"- {item}", STYLES["bullet"]))
    return result


def callout(title: str, body: str, tone: str = "blue") -> Table:
    background = {
        "blue": PALE_BLUE,
        "teal": PALE_TEAL,
        "amber": PALE_AMBER,
        "red": PALE_RED,
    }[tone]
    content = [
        paragraph(title, "callout"),
        Spacer(1, 2),
        paragraph(body, "body"),
    ]
    table = Table([[content]], colWidths=[165 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, TEAL if tone == "teal" else LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def data_table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    rendered = [[paragraph(value, "table_header") for value in headers]]
    rendered.extend([[paragraph(str(value), "table_body") for value in row] for row in rows])
    table = Table(rendered, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F7F9FB")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def cover(title: str, subtitle: str, meta: str) -> list:
    return [
        Spacer(1, 48 * mm),
        paragraph(title, "cover_title"),
        Spacer(1, 4 * mm),
        paragraph(subtitle, "cover_subtitle"),
        Spacer(1, 12 * mm),
        paragraph(meta, "cover_meta"),
        PageBreak(),
    ]


def build_pdf(filename: str, title: str, story: list) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / filename
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="Purchasing Tool Project",
        subject="Final delivery guidance",
    )
    document.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    return output_path


def user_guide_story() -> list:
    story = cover(
        "Purchasing Tool<br/>Complete User Guide",
        "How to use every tab, review recommendations, and create safe local purchase orders.",
        "Version reviewed: GitHub c5e799e plus final-delivery CSV improvements | 31 July 2026",
    )
    story += [
        paragraph("1. Start Here", "h1"),
        paragraph(
            "The tool brings together the product catalogue, supplier assignments, demand history, "
            "forecast readiness, recommendations, seasonality, and local purchase orders. It is an "
            "admin tool: actions change purchasing data and should be completed by an approved operator.",
        ),
        callout(
            "Important safety boundary",
            "Mark as locally issued changes only the local PO status. It does not create an OrderPro PO, "
            "email a supplier, or send an order externally.",
            "amber",
        ),
        paragraph("Login and navigation", "h2"),
        *bullets(
            [
                "Sign in with the configured administrator email and password when authentication is enabled.",
                "Use the main Search box to find a Product ID, SKU, barcode, supplier, or product name.",
                "Use the tabs from left to right for the normal workflow. The final three tabs are specialist cleanup and legacy-mapping tools.",
                "Use internal Product ID for exact product lookup. OrderPro SKU is the main external product identity.",
            ]
        ),
        paragraph("Recommended daily workflow", "h2"),
        data_table(
            ["Step", "Tab", "Operator outcome"],
            [
                ["1", "Products", "Find the product and confirm its current stock and supplier context."],
                ["2", "Supplier Cleanup / Mapping", "Resolve a missing or uncertain supplier before purchasing."],
                ["3", "Demand History", "Confirm recent and historical demand coverage."],
                ["4", "Forecast Readiness", "Resolve blockers and review warnings."],
                ["5", "Forecast / Supplier Forecast", "Review quantity, risk, and supplier-grouped demand."],
                ["6", "Recommendations", "Accept, reject, or escalate the recommendation."],
                ["7", "Purchase Orders", "Create, preflight, approve, and locally issue the PO."],
            ],
            [15 * mm, 42 * mm, 108 * mm],
        ),
        PageBreak(),
        paragraph("2. Tab-by-Tab Reference", "h1"),
    ]

    tabs = [
        (
            "Products",
            "Search and review the active product catalogue.",
            [
                "Search by internal Product ID, OrderPro SKU, barcode, or name.",
                "Expand a row to inspect supplier and product context.",
                "Select products and use Generate Draft PO to group valid products by their canonical supplier.",
                "Review the created and skipped product summary before opening a generated PO.",
            ],
            "Use this as the normal starting point. A missing supplier, non-positive quantity, or other readiness issue can cause a product to be skipped.",
        ),
        (
            "Supplier Mapping",
            "Review legacy ProductSupplier mappings and their confidence state.",
            [
                "Confirm a mapping when the supplier-product relationship is verified.",
                "Reject an incorrect mapping.",
                "Set or unset the preferred legacy mapping when multiple historical mappings exist.",
            ],
            "The future source of truth is Product.supplier_id from OrderPro. Treat this tab mainly as transition and audit support.",
        ),
        (
            "Supplier Cleanup",
            "Assign the canonical active supplier to products that are missing one.",
            [
                "Filter and sort candidates by priority, SKU, product name, stock, or open demand.",
                "Open a candidate, search active suppliers, and select the verified supplier.",
                "Record the reviewer and notes, then assign locally.",
                "If evidence is insufficient, defer, reject, or mark that more information is needed.",
            ],
            "Assignments are local only. The tool does not create suppliers or write changes back to OrderPro.",
        ),
        (
            "Demand History",
            "Measure which products have usable historical demand.",
            [
                "Review coverage summary cards and the date range.",
                "Filter products with history or missing history and filter by supplier.",
                "Sort by latest demand date, row count, months covered, last 90 days, SKU, or product name.",
                "Open a product for detailed coverage and export the current filtered coverage CSV.",
            ],
            "The on-screen import commands are local operator commands. Run a dry-run and review ambiguity reports before any apply step.",
        ),
        (
            "Forecast Readiness",
            "Show whether each product has enough trusted inputs for purchasing.",
            [
                "Filter by Ready, Partially Ready, Blocked, or Monitor Only.",
                "Filter by missing input or supplier, then sort by readiness score, status, SKU, stock, or open demand.",
                "Open a product to see input sources, warnings, blockers, and recommended action.",
                "Use the linked cleanup areas to resolve supplier or demand-history gaps.",
                "Export the filtered readiness CSV for review.",
            ],
            "Blocked means a required purchasing input is absent. Partially Ready means purchasing can be reviewed but warnings remain. Monitor Only means there is no current demand signal.",
        ),
        (
            "Forecast",
            "Inspect the full forecast for one product.",
            [
                "Enter the internal Product ID.",
                "Review current stock, open demand, demand source, recommended action, and quantity.",
                "Inspect Forecast Inputs to see supplier, demand, inventory, cost, lead-time, MOQ, and pack sources.",
                "Review incoming stock and the supplier context before acting.",
            ],
            "A forecast is decision support. Confirm stale-demand warnings, pack rules, and supplier mapping before making a PO.",
        ),
        (
            "Supplier Forecast",
            "Review reorder needs grouped under one supplier.",
            [
                "Choose a supplier and load its product forecast.",
                "Filter All, Needs Reorder, High Risk, Open Demand, No History, or Missing Lead Time.",
                "Review each product's action, quantity, stock, and risk.",
                "Generate a draft PO from eligible reorder rows, then open the created PO.",
            ],
            "This is the fastest route for supplier-level purchasing, but skipped rows still require individual cleanup.",
        ),
        (
            "Seasonality",
            "Review recurring seasonal patterns and current seasonal risk.",
            [
                "Select the as-of date used for classification.",
                "Filter by current status, recurring pattern, season, confidence, stock status, supplier status, or saved views.",
                "Use saved views for in-season out-of-stock, approaching-season low-stock, and missing-input reviews.",
                "Open a product to inspect monthly values and the seasonality forecast summary.",
            ],
            "High-confidence seasonality can support timing decisions. Insufficient-data rows should not be treated as reliable seasonal evidence.",
        ),
        (
            "Recommendations",
            "Create and review reorder decisions before PO conversion.",
            [
                "Use Manager Review Summary to see the queue and export focused review lists.",
                "Generate a reorder recommendation by Product ID when needed.",
                "Inspect forecast and supplier snapshots plus the PO Readiness panel.",
                "Accept a safe recommendation or reject it with a reason.",
                "Convert only an accepted, PO-ready recommendation into a draft PO.",
                "For stale demand, record Watchlist, Manager approved one-time, Reject stale, or Wait for recent demand.",
            ],
            "Manager approved one-time is an exception workflow, not a replacement for fresh demand history.",
        ),
        (
            "Purchase Orders",
            "Manage the safe local PO workflow.",
            [
                "Create a draft directly or open one created from products, supplier forecast, or recommendations.",
                "Add or edit lines only while the PO is Draft.",
                "Review PO Preflight blockers and warnings.",
                "Submit for Approval, enter Approved by, Approve, then Mark as locally issued.",
                "Use Export Clean CSV for an uncluttered spreadsheet.",
                "Use Download handoff packet only after local issue when technical handoff files are required.",
                "Mark Received after goods are received, or Cancel before issue where allowed.",
            ],
            "The state flow is Draft -> Pending Approval -> Approved -> Issued -> Received. Cancel is available only before issue.",
        ),
        (
            "Supplier Assignment Review",
            "Review supplier suggestions derived from evidence such as prior OrderPro purchase orders.",
            [
                "Filter by confidence and review status.",
                "Inspect the evidence summary and suggested supplier.",
                "Confirm the verified supplier, optionally using a manual supplier choice.",
                "Reject unsupported suggestions without changing the product's canonical supplier.",
            ],
            "A suggestion remains non-authoritative until explicitly confirmed.",
        ),
        (
            "Unmapped Products",
            "Create a legacy mapping for products with no ProductSupplier record.",
            [
                "Enter product and supplier IDs plus any verified supplier SKU, price, MOQ, pack size, currency, or lead time.",
                "Create the mapping only when the relationship is known.",
            ],
            "Prefer Supplier Cleanup for the canonical direct supplier assignment. This tab exists for legacy mapping support.",
        ),
        (
            "Weak Mappings",
            "Resolve pending or low-confidence legacy mappings.",
            [
                "Review the match method and evidence.",
                "Confirm correct mappings or reject incorrect ones.",
            ],
            "Do not confirm a weak mapping based only on a similar name.",
        ),
    ]

    for index, (name, purpose, actions, caution) in enumerate(tabs, start=1):
        story.append(KeepTogether([paragraph(f"2.{index} {name}", "h2"), paragraph(purpose)] + bullets(actions)))
        story.append(callout("Operator note", caution, "teal" if index < 10 else "blue"))
        if index in {3, 6, 9, 11}:
            story.append(PageBreak())

    story += [
        PageBreak(),
        paragraph("3. Status Glossary", "h1"),
        data_table(
            ["Status", "Meaning", "What to do"],
            [
                ["Ready", "Required purchasing inputs are available.", "Review warnings, then proceed through recommendation and PO controls."],
                ["Partially Ready", "No hard blocker, but one or more warnings remain.", "Review missing cost, lead time, pack size, fallback MOQ, or other warnings."],
                ["Blocked", "A required identity, supplier, stock, or purchasing condition is missing.", "Resolve the blocker before creating or approving a PO."],
                ["Monitor Only", "No current demand signal supports a reorder.", "Do not reorder automatically; continue monitoring."],
                ["Pending Review", "A recommendation or assignment needs a human decision.", "Inspect evidence and accept, reject, confirm, or defer."],
                ["Locally Issued", "The local PO status changed to issued.", "Use the handoff packet if needed. Nothing has been sent to OrderPro."],
            ],
            [30 * mm, 62 * mm, 73 * mm],
        ),
        paragraph("4. End-of-Day Checks", "h1"),
        *bullets(
            [
                "No blocked recommendation was converted to a PO.",
                "Every approved PO has a verified active supplier and positive quantities.",
                "Pack, MOQ, lead-time, and cost warnings were reviewed.",
                "Any one-time stale-demand decision includes reviewer and notes.",
                "Clean CSV and handoff downloads were stored with the correct PO reference.",
                "No operator treated local issue as an external OrderPro send.",
            ]
        ),
    ]
    return story


def orderpro_guide_story() -> list:
    story = cover(
        "Purchase Orders and<br/>OrderPro Handoff Guide",
        "Current safe workflow, clean CSV export, local handoff packet, and the future controlled forwarding design.",
        "Current external-send capability: NOT IMPLEMENTED | 31 July 2026",
    )
    story += [
        paragraph("1. Current Delivery Boundary", "h1"),
        callout(
            "What works today",
            "The tool can create a local draft, run preflight, submit for approval, approve, mark locally issued, "
            "export a clean CSV, and download a technical handoff packet for an issued PO.",
            "teal",
        ),
        callout(
            "What does not happen today",
            "No OrderPro purchase order is created. No supplier email is sent. No external API write is performed. "
            "External Send Readiness intentionally remains false.",
            "red",
        ),
        paragraph("Safe PO workflow", "h2"),
        data_table(
            ["State", "Operator action", "System effect"],
            [
                ["Draft", "Create PO and edit lines.", "Local data only; quantities and costs can still change."],
                ["Pending Approval", "Submit after preflight.", "Locks normal line editing and starts review."],
                ["Approved", "Record the approver.", "Confirms local authorization; still not sent."],
                ["Issued", "Mark as locally issued.", "Changes local status and enables handoff packet download."],
                ["Received", "Record receipt.", "Closes the local receiving stage."],
            ],
            [32 * mm, 57 * mm, 76 * mm],
        ),
        paragraph("2. Export Clean CSV", "h1"),
        paragraph(
            "Use Export Clean CSV when a manager or operator needs a readable spreadsheet. The export has one row "
            "per PO line and removes technical IDs, audit timestamps, contact fields, stock fields, product descriptions, "
            "and duplicated totals.",
        ),
        data_table(
            ["Included fields", "Why they are included"],
            [
                ["PO Number, Supplier, Status, Expected Delivery", "Essential order context."],
                ["SKU, Product, Supplier SKU", "Human and supplier product identification."],
                ["Quantity, Pack Size, Packs, MOQ", "Ordering quantity and pack-rule context."],
                ["Unit Cost, Line Total, Currency", "Commercial review."],
                ["Notes", "Line-specific operator context."],
            ],
            [75 * mm, 90 * mm],
        ),
        *bullets(
            [
                "The CSV opens cleanly in Microsoft Excel using UTF-8 with BOM.",
                "Formula-like text beginning with =, +, -, or @ is neutralized for spreadsheet safety.",
                "Packs is quantity divided by pack size and stays blank when pack size is unavailable.",
                "The export is read-only and can be used before or after approval when the PO has lines.",
            ]
        ),
        PageBreak(),
        paragraph("3. Local Handoff Packet", "h1"),
        paragraph(
            "Download handoff packet is available only for a locally issued PO. The ZIP is intended for controlled "
            "review and future integration work, not as proof that an external order exists.",
        ),
        data_table(
            ["File", "Contents"],
            [
                ["purchase_order.json", "Local PO header, supplier details, totals, status, schema version, and explicit false external-send flags."],
                ["purchase_order_lines.csv", "Technical line identity, OrderPro product linkage, quantity, cost, MOQ, and pack context."],
                ["README.txt", "Safety notice, contents summary, and the current no-send boundary."],
            ],
            [52 * mm, 113 * mm],
        ),
        paragraph("4. Future OrderPro Forwarding Design", "h1"),
        callout(
            "Gate before implementation",
            "Continue using a read-only OrderPro token for discovery and sync. Do not introduce a write-capable token "
            "until the exact private OrderPro purchase-order contract, permissions, staging target, and approval process are verified.",
            "amber",
        ),
        paragraph("Planned controlled sequence", "h2"),
        data_table(
            ["Stage", "Required behavior"],
            [
                ["1. Contract discovery", "Confirm the exact private OrderPro PO-create endpoint, request schema, required identifiers, statuses, and error rules. Do not guess the endpoint."],
                ["2. Payload preview", "Generate a read-only preview from the issued local PO. Show supplier, line identities, quantities, costs, and warnings before sending."],
                ["3. Pre-send validation", "Require local status Issued, zero preflight blockers, an active canonical supplier, OrderPro product IDs or SKUs, and positive quantities."],
                ["4. Explicit approval", "Require a separate Confirm Forward to OrderPro action. Do not reuse Mark as locally issued as consent to send."],
                ["5. Idempotent create", "Send one create request with a stable local PO reference or idempotency key so retries cannot create duplicate OrderPro POs."],
                ["6. Persist linkage", "Store the returned OrderPro PO ID, creation time, response status, and audit record against the local PO."],
                ["7. Reconcile", "Read the OrderPro PO back and compare supplier, products, quantities, and totals with the local snapshot."],
                ["8. Ongoing sync", "Refresh OrderPro status and receiving changes without overwriting the original approval audit."],
            ],
            [37 * mm, 128 * mm],
        ),
        paragraph("Failure and retry rules", "h2"),
        *bullets(
            [
                "A timeout must result in Unknown, not Failed, until OrderPro is checked for an already-created PO.",
                "Never retry a create call without first checking the idempotency key or stored OrderPro linkage.",
                "Partial line acceptance must block completion and display the exact rejected lines.",
                "A write failure must not roll back or erase the approved local PO.",
                "Supplier communication must remain a separate feature from OrderPro PO creation.",
            ]
        ),
        PageBreak(),
        paragraph("5. Acceptance Tests Before Write-Back", "h1"),
        *bullets(
            [
                "Preview matches the approved local PO exactly.",
                "Missing OrderPro supplier or product identity blocks sending.",
                "Duplicate clicks and retries create only one OrderPro PO.",
                "401, 403, 409, 429, 5xx, and timeout responses have safe operator messages.",
                "The returned OrderPro PO is fetched and reconciled.",
                "Audit history records who approved, who sent, when, and which remote ID was created.",
                "A staging dry-run and one controlled real test are signed off before production enablement.",
            ]
        ),
    ]
    return story


def delivery_checklist_story() -> list:
    story = cover(
        "Purchasing Tool<br/>Final Delivery Audit",
        "Verified repository state, missing local work, release blockers, and the shortest safe path to handoff.",
        "Audit date: 31 July 2026 | Canonical branch: orderpro-source-of-truth",
    )
    story += [
        paragraph("1. Executive Status", "h1"),
        data_table(
            ["Area", "Status", "Evidence / decision"],
            [
                ["GitHub branch", "Verified", "Remote orderpro-source-of-truth is at c5e799e."],
                ["Local PO handoff", "Implemented", "OP-46 is present in remote history at 7d7cde4."],
                ["OrderPro reads", "Implemented but gated", "Pagination and rate-limit handling are present at c5e799e; production credentials and dry-run verification remain."],
                ["OrderPro writes", "Not implemented", "The app intentionally reports external sending as unsupported."],
                ["Database/data", "Operator verified", "The working database and the latest uploaded data were confirmed correct on 31 July 2026."],
                ["Frontend", "Passing", "169 tests passed and the production build completed during this audit."],
                ["Backend", "Passing locally", "571 tests passed after correcting the remote baseline's 3 date-sensitive failures and adding safeguard coverage."],
                ["CSV export", "Improved locally", "The purchase-order export is reduced from 34 technical fields to 15 operational fields."],
                ["Inactive products", "Rebuilt locally", "Inactive products are hidden from working queues and blocked from new recommendations and draft POs."],
                ["User documentation", "Created", "Complete user, PO/OrderPro, and final-delivery PDF guides generated and visually checked."],
            ],
            [43 * mm, 32 * mm, 90 * mm],
        ),
        callout(
            "Release definition",
            "The tool can be delivered safely as a local purchasing and handoff system after deployment and data verification. "
            "Automated OrderPro PO creation is a separate gated phase. If automated forwarding is required for initial delivery, it remains a release blocker.",
            "amber",
        ),
        paragraph("2. GitHub vs. Last Local Version", "h1"),
        paragraph(
            "The exact local commit 3306389 is not present on any remote ref or in the clean Windows checkout. "
            "The comparison below separates verified GitHub evidence, the behavior rebuilt and tested during this audit, "
            "and the parts of the earlier recorded summary that still cannot be recovered exactly.",
        ),
        data_table(
            ["Capability", "Verified current state", "Earlier recorded summary"],
            [
                ["Guarded cleanup importer", "Existing supplier-cleanup import exists, but the later final guarded workflow is not verifiable in the remote tree.", "Recorded as dry-run, reviewer approval, and apply controls."],
                ["Inactive product handling", "Rebuilt locally: normal product, recommendation, mapping, and supplier-cleanup queues exclude inactive products; new recommendations and draft POs are blocked. Regression tests pass.", "Recorded as hiding inactive products and blocking new reorder recommendations."],
                ["Draft deactivation cleanup", "Not verified as the later local implementation.", "Recorded as local deactivation of drafts."],
                ["Module import fix", "Current scripts include root-path setup in several places, but the exact later diff is unavailable.", "Recorded as fixing ModuleNotFoundError for operator scripts."],
                ["Operator instructions", "Multiple technical docs exist, but the exact later handoff instructions are not recoverable from GitHub.", "Recorded as added and tested."],
            ],
            [49 * mm, 58 * mm, 58 * mm],
        ),
        callout(
            "Reconciliation decision",
            "The clean Windows checkout confirms that 3306389 is unavailable, so exact recovery is closed as unsuccessful. "
            "Use the reviewed replacement patch for the verified behaviors. Do not label any reconstructed work as the exact missing commit.",
            "amber",
        ),
        paragraph("3. Remaining Work - Required Before Handoff", "h1"),
        data_table(
            ["Priority", "Owner", "Task", "Completion evidence"],
            [
                ["P0", "Zain / repo owner", "Review and apply the tested replacement patch; record 3306389 as unavailable rather than recovered.", "Canonical branch contains the reviewed equivalent behavior and its tests."],
                ["P0", "Deployment owner", "Back up the confirmed database and verify the deployed backend points to that intended database.", "Backup is retained; Alembic upgrade succeeds; backend health and data counts are green."],
                ["P0", "Deployment owner", "Deploy backend and frontend from the reviewed branch.", "Login, CORS, data load, and core tabs pass smoke testing."],
                ["P0", "Admin", "Enable matching authentication flags on backend and frontend.", "AUTH_ENABLED=true and VITE_AUTH_ENABLED=true; admin login succeeds."],
                ["P0", "OrderPro admin", "Provide a read-only token for suppliers, products, inventory, and orders.", "Dry-run sync completes; ORDERPRO_SYNC_ENABLED remains false until reviewed."],
                ["P0", "Data owner", "Confirm whether any OrderPro-side deactivation remains after the latest successful data load.", "Authoritative active/inactive counts are archived and reviewed."],
                ["P1", "Data reviewer", "Review 17 ambiguous reused-SKU groups.", "Each group has an explicit mapping, split, or leave-unresolved decision."],
                ["P1", "Operator", "Run cleanup/import dry-run, review report, then apply with reviewer name.", "Saved dry-run and apply reports agree with approved decisions."],
                ["P1", "Data owner", "Import demand history, rebuild seasonality, and recheck forecast coverage.", "Coverage, date range, seasonality, and readiness summaries are accepted."],
                ["P1", "Manager", "Complete UAT on recommendation-to-local-PO workflow.", "Signed checklist for create, approve, issue, export, handoff, receive, and cancel controls."],
                ["P2", "Project owner", "Post final #systems delivery update.", "Manager-facing summary includes delivered scope and known OrderPro write-back boundary."],
            ],
            [15 * mm, 29 * mm, 73 * mm, 48 * mm],
        ),
        paragraph("Data constraints that remain binding", "h2"),
        *bullets(
            [
                "OrderPro is the only source for unavailable costs. Do not guess or backfill the 642 missing costs from unrelated sheets.",
                "Use read-only OrderPro access during discovery and data synchronization.",
                "Do not call OrderPro write endpoints until the controlled write-back phase is separately approved.",
                "Keep local and staging data separate; recreating Render Postgres must not affect local PostgreSQL.",
            ]
        ),
        PageBreak(),
        paragraph("4. Final Verification Checklist", "h1"),
        data_table(
            ["Check", "Pass condition"],
            [
                ["Repository", "Clean reviewed diff; intended branch; no lost local commit; version tag or delivery commit recorded."],
                ["Backend", "Full pytest suite passes; Alembic has one head; clean database migration succeeds."],
                ["Frontend", "All tests pass; production build succeeds; no console errors in the supported browser."],
                ["Security", "Secret scan passes; authentication enabled; no raw OrderPro payloads, tokens, .env files, or customer data committed."],
                ["Deployment", "Health endpoint, login, CORS, API URL, database, and migrations verified on Render."],
                ["Data", "Product, supplier, inventory, order, demand-history, cost, and seasonality counts reconciled."],
                ["Workflow", "Products -> readiness -> recommendation -> draft PO -> approval -> local issue -> clean CSV/handoff tested."],
                ["Boundary", "UI and training materials state that local issue does not send to OrderPro."],
                ["Rollback", "Database backup/export and previous deploy reference retained before final data apply."],
            ],
            [48 * mm, 117 * mm],
        ),
        paragraph("5. Suggested Delivery Sign-Off", "h1"),
        *bullets(
            [
                "Technical sign-off: tests, migrations, secret scan, and deployment smoke tests.",
                "Data sign-off: counts, costs, supplier mapping, demand coverage, and ambiguous groups.",
                "Operational sign-off: user follows the complete workflow using the guide without developer assistance.",
                "Scope sign-off: stakeholders accept local handoff now and the separate future OrderPro write-back plan.",
            ]
        ),
    ]
    return story


def main() -> int:
    outputs = [
        build_pdf(
            "Purchasing_Tool_Complete_User_Guide.pdf",
            "Purchasing Tool Complete User Guide",
            user_guide_story(),
        ),
        build_pdf(
            "Purchasing_Tool_PO_and_OrderPro_Guide.pdf",
            "Purchasing Tool PO and OrderPro Guide",
            orderpro_guide_story(),
        ),
        build_pdf(
            "Purchasing_Tool_Final_Delivery_Audit.pdf",
            "Purchasing Tool Final Delivery Audit",
            delivery_checklist_story(),
        ),
    ]
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
