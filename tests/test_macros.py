"""Tests for Jinja2 UI macros in app/templates/macros/_ui.html."""
import pytest


def _render(app, tpl_str):
    """Render a Jinja2 template string inside an app context."""
    with app.app_context():
        from flask import render_template_string
        return render_template_string(tpl_str)


# ---------------------------------------------------------------------------
# delta_badge
# ---------------------------------------------------------------------------

def test_delta_badge_positive(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import delta_badge %}'
        '{{ delta_badge(5.3) }}',
    )
    assert "text-green-600" in html
    assert "+5.3" in html
    assert "vs. anterior" in html


def test_delta_badge_negative(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import delta_badge %}'
        '{{ delta_badge(-2.1) }}',
    )
    assert "text-red-500" in html
    assert "-2.1" in html


def test_delta_badge_zero(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import delta_badge %}'
        '{{ delta_badge(0) }}',
    )
    assert "sem variação" in html


def test_delta_badge_none(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import delta_badge %}'
        '{{ delta_badge(none) }}',
    )
    # The macro renders "— vs. período anterior" for None
    assert "—" in html


# ---------------------------------------------------------------------------
# kpi_card_simple
# ---------------------------------------------------------------------------

def test_kpi_card_simple_renders_label_and_value(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import kpi_card_simple %}'
        '{{ kpi_card_simple("Simulações", "42") }}',
    )
    assert "Simulações" in html
    assert "42" in html
    assert "rounded-xl" in html


def test_kpi_card_simple_custom_class(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import kpi_card_simple %}'
        '{{ kpi_card_simple("Margem", "24.5%", "text-green-600") }}',
    )
    assert "text-green-600" in html
    assert "24.5%" in html


# ---------------------------------------------------------------------------
# section_card
# ---------------------------------------------------------------------------

def test_section_card_with_title(app):
    html = _render(
        app,
        '{% import "macros/_ui.html" as ui %}'
        '{% call ui.section_card(title="Dados Pessoais") %}'
        "<p>conteúdo</p>"
        "{% endcall %}",
    )
    assert "Dados Pessoais" in html
    assert "conteúdo" in html
    assert "rounded-xl" in html


def test_section_card_no_title_omits_h2(app):
    html = _render(
        app,
        '{% import "macros/_ui.html" as ui %}'
        "{% call ui.section_card() %}"
        "<p>só conteúdo</p>"
        "{% endcall %}",
    )
    assert "só conteúdo" in html
    assert "<h2" not in html


# ---------------------------------------------------------------------------
# page_header
# ---------------------------------------------------------------------------

def test_page_header_renders_title_and_back_link(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import page_header %}'
        '{{ page_header("Produtos", "/produtos") }}',
    )
    assert "Produtos" in html
    assert "/produtos" in html
    assert "mb-6" in html  # default mb value


def test_page_header_with_subtitle(app):
    html = _render(
        app,
        '{% from "macros/_ui.html" import page_header %}'
        '{{ page_header("Relatório", "/relatorios", subtitle="Dados do mês") }}',
    )
    assert "Relatório" in html
    assert "Dados do mês" in html
