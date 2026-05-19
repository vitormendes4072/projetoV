from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Paleta de cores VEntregaz
# ---------------------------------------------------------------------------
_BLUE = colors.HexColor("#0d80f2")
_DARK = colors.HexColor("#0d141c")
_SLATE = colors.HexColor("#49739c")
_BG_HEADER = colors.HexColor("#e7edf4")
_GREEN = colors.HexColor("#16a34a")
_RED = colors.HexColor("#dc2626")
_STRIPE = colors.HexColor("#f8fafc")

_MONTH_NAMES = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "rpt_title",
            parent=base["Normal"],
            fontSize=20,
            textColor=_DARK,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "rpt_subtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=_SLATE,
            fontName="Helvetica",
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "kpi_value": ParagraphStyle(
            "rpt_kpi_value",
            parent=base["Normal"],
            fontSize=18,
            textColor=_BLUE,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "kpi_label": ParagraphStyle(
            "rpt_kpi_label",
            parent=base["Normal"],
            fontSize=8,
            textColor=_SLATE,
            fontName="Helvetica",
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "rpt_th",
            parent=base["Normal"],
            fontSize=8,
            textColor=_DARK,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "rpt_td",
            parent=base["Normal"],
            fontSize=8,
            textColor=_DARK,
            fontName="Helvetica",
            alignment=TA_LEFT,
        ),
        "table_cell_right": ParagraphStyle(
            "rpt_td_r",
            parent=base["Normal"],
            fontSize=8,
            textColor=_DARK,
            fontName="Helvetica",
            alignment=TA_RIGHT,
        ),
        "footer": ParagraphStyle(
            "rpt_footer",
            parent=base["Normal"],
            fontSize=7,
            textColor=_SLATE,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "empty": ParagraphStyle(
            "rpt_empty",
            parent=base["Normal"],
            fontSize=10,
            textColor=_SLATE,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
    }


def build_monthly_pdf(report: dict[str, Any]) -> bytes:
    """Gera o PDF do relatório mensal de margem e retorna os bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Relatório Mensal VEntregaz — {_MONTH_NAMES[report['month']]}/{report['year']}",
        author="VEntregaz",
    )

    s = _styles()
    page_w = A4[0] - 4 * cm  # usable width
    story = []

    # ------------------------------------------------------------------
    # Cabeçalho
    # ------------------------------------------------------------------
    month_label = f"{_MONTH_NAMES[report['month']]}/{report['year']}"
    story.append(Paragraph("VEntregaz", s["title"]))
    story.append(Paragraph(f"Relatório Mensal de Margem — {month_label}", s["subtitle"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_BLUE))
    story.append(Spacer(1, 0.5 * cm))

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------
    kpi_data = [
        [
            Paragraph(str(report["total"]), s["kpi_value"]),
            Paragraph(f"{report['avg_margin']:.1f}%", s["kpi_value"]),
            Paragraph(f"{report['avg_roi']:.1f}%", s["kpi_value"]),
            Paragraph(f"{report['pct_profitable']:.0f}%", s["kpi_value"]),
        ],
        [
            Paragraph("Simulações", s["kpi_label"]),
            Paragraph("Margem Média", s["kpi_label"]),
            Paragraph("ROI Médio", s["kpi_label"]),
            Paragraph("% Lucrativas", s["kpi_label"]),
        ],
    ]
    col_w = page_w / 4
    kpi_table = Table(kpi_data, colWidths=[col_w] * 4, rowHeights=[0.9 * cm, 0.5 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _BG_HEADER),
        ("BOX", (0, 0), (-1, -1), 0.5, _BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.white),
        ("ROUNDEDCORNERS", [4]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.6 * cm))

    # ------------------------------------------------------------------
    # Tabela de simulações
    # ------------------------------------------------------------------
    if not report["rows"]:
        story.append(Paragraph("Nenhuma simulação registrada neste mês.", s["empty"]))
    else:
        headers = ["Data", "Título", "Preço (R$)", "Custo (R$)", "Lucro Liq. (R$)", "Margem %", "ROI %"]
        col_widths = [
            1.8 * cm,   # Data
            5.5 * cm,   # Título
            2.3 * cm,   # Preço
            2.3 * cm,   # Custo
            2.8 * cm,   # Lucro Liq.
            2.0 * cm,   # Margem %
            1.9 * cm,   # ROI %
        ]

        table_data = [[Paragraph(h, s["table_header"]) for h in headers]]

        for idx, row in enumerate(report["rows"]):
            margin_val = float(row.margin)
            profit_val = float(row.net_profit)
            margin_color = _GREEN if margin_val > 0 else _RED

            margin_style = ParagraphStyle(
                f"mg_{idx}",
                parent=s["table_cell_right"],
                textColor=margin_color,
                fontName="Helvetica-Bold",
            )
            profit_style = ParagraphStyle(
                f"pf_{idx}",
                parent=s["table_cell_right"],
                textColor=margin_color,
            )

            title_text = (row.title or "Simulação")
            if len(title_text) > 30:
                title_text = title_text[:28] + "…"

            table_data.append([
                Paragraph(row.created_at.strftime("%d/%m/%Y"), s["table_cell"]),
                Paragraph(title_text, s["table_cell"]),
                Paragraph(f"{float(row.price):,.2f}", s["table_cell_right"]),
                Paragraph(f"{float(row.cost):,.2f}", s["table_cell_right"]),
                Paragraph(f"{profit_val:,.2f}", profit_style),
                Paragraph(f"{margin_val:.1f}%", margin_style),
                Paragraph(f"{float(row.roi):.1f}%", s["table_cell_right"]),
            ])

        sim_table = Table(table_data, colWidths=col_widths, repeatRows=1)

        row_bg = []
        for i in range(1, len(table_data)):
            bg = _STRIPE if i % 2 == 0 else colors.white
            row_bg.append(("BACKGROUND", (0, i), (-1, i), bg))

        sim_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _BG_HEADER),
            ("LINEBELOW", (0, 0), (-1, 0), 1, _BLUE),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, _SLATE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _STRIPE]),
            ("ALIGN", (0, 0), (1, -1), "LEFT"),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            *row_bg,
        ]))
        story.append(sim_table)

    # ------------------------------------------------------------------
    # Rodapé
    # ------------------------------------------------------------------
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_SLATE))
    story.append(Spacer(1, 0.2 * cm))
    generated_at = datetime.now().strftime("%d/%m/%Y às %H:%M")
    story.append(Paragraph(f"Gerado em {generated_at} pelo VEntregaz", s["footer"]))

    doc.build(story)
    return buffer.getvalue()
