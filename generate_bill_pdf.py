"""
Generate RA-04 Bill PDF
Kaveri Infrasystems / Assignment Three

Produces the client-facing RA-04 bill PDF, reusing bill_engine.py's own
compute_bill() so the PDF can never disagree with the bill actually
written into ClickUp — one calculation, two outputs (a ClickUp task and
this PDF), never two separate calculations that could drift apart.

Usage:
    python generate_bill_pdf.py

Output:
    RA-04_Bill.pdf in the current folder.

Environment (.env): reuses the same List IDs as bill_engine.py.
"""

import os
import sys
import importlib.util
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

_be_spec = importlib.util.spec_from_file_location(
    "bill_engine", os.path.join(os.path.dirname(__file__), "bill_engine.py"))
bill_engine = importlib.util.module_from_spec(_be_spec)
_be_spec.loader.exec_module(bill_engine)

BOQ_DESCRIPTIONS = {
    "B01": "Detailed engineering and design",
    "B02": "Supply of GI cable tray, 300mm",
    "B03": "Supply of CCTV pole, 9m",
    "B04": "OFC laying including HDD crossing",
    "B05": "Cable tray installation",
    "B06": "CCTV pole erection incl. foundation",
    "B07": "Testing and commissioning",
}


def build_pdf(result, output_path="RA-04_Bill.pdf"):
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                             topMargin=18 * mm, bottomMargin=18 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("RightAlign", parent=styles["Normal"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle("Center", parent=styles["Normal"], alignment=TA_CENTER))
    styles.add(ParagraphStyle("SmallNote", parent=styles["Normal"], fontSize=8, textColor=colors.grey))

    story = []

    # --- Header ---
    story.append(Paragraph("KAVERI INFRASYSTEMS", styles["Title"]))
    story.append(Paragraph("Running Account Bill", styles["Heading2"]))
    story.append(Spacer(1, 4 * mm))

    header_data = [
        ["Bill No.:", "RA-04", "Work Month:", result["work_month"]],
        ["Project:", "SCP2 - Smart Corridor Package 2", "Date:", datetime.date.today().isoformat()],
    ]
    header_table = Table(header_data, colWidths=[28 * mm, 65 * mm, 28 * mm, 50 * mm])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 6 * mm))

    # --- Line items table ---
    table_data = [["BOQ Item", "Description", "Basis", "Billed Qty", "Rate (Rs.)", "Value (Rs.)"]]
    for li in result["line_items"]:
        table_data.append([
            li["boq_item"],
            BOQ_DESCRIPTIONS.get(li["boq_item"], ""),
            li["basis"],
            f"{li['billable_qty']:,.2f}",
            f"{li['rate']:,.2f}",
            f"{li['value']:,.2f}",
        ])

    line_table = Table(table_data, colWidths=[18*mm, 55*mm, 22*mm, 22*mm, 25*mm, 28*mm], repeatRows=1)
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 3 * mm))

    # --- Exclusions / notes ---
    note_lines = []
    for li in result["line_items"]:
        for n in li["notes"]:
            note_lines.append(f"<b>{li['boq_item']}:</b> {n}")
    if note_lines:
        story.append(Paragraph("Notes on exclusions and adjustments:", styles["Heading4"]))
        for line in note_lines:
            story.append(Paragraph(f"&bull; {line}", styles["Normal"]))
        story.append(Spacer(1, 4 * mm))

    # --- Summary ---
    summary_data = [
        ["Gross Value", f"Rs. {result['gross']:,.2f}"],
        ["Add: GST @ 18%", f"Rs. {result['gst']:,.2f}"],
        ["Less: Retention @ 5%", f"Rs. {result['retention']:,.2f}"],
        ["Less: Advance Recovery", f"Rs. {result['advance_recovery']:,.2f}"],
        ["NET PAYABLE", f"Rs. {result['net_payable']:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[90 * mm, 50 * mm])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -2), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 3),
    ]))
    story.append(Spacer(1, 4 * mm))
    story.append(summary_table)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(
        "This bill is generated by an automated RA billing engine reading certified quantities, "
        "delivery/QC status, and contract terms directly from the project management system. "
        "Every figure above is computed in code, cross-checked against contract clauses 2 and 3, "
        "and no figure is estimated or entered manually.",
        styles["SmallNote"]))

    doc.build(story)
    return output_path


def run():
    boq = bill_engine.fetch_boq(bill_engine.BOQ_LIST_ID)
    mc_data = bill_engine.fetch_measurement_certification(bill_engine.MEASUREMENT_LIST_ID)
    production_orders = bill_engine.fetch_production_orders(bill_engine.PRODUCTION_ORDERS_LIST_ID)
    cumulative_before = bill_engine.load_cumulative_billed()
    prior_bills = bill_engine.load_bill_register()

    result = bill_engine.compute_bill(boq, mc_data, production_orders, cumulative_before, prior_bills)
    path = build_pdf(result)
    print(f"RA-04 bill PDF written to {path}")
    print(f"Net payable: Rs.{result['net_payable']:,.2f}")


if __name__ == "__main__":
    run()
