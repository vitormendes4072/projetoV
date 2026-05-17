from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app import db
from app.models.custo_fixo import CustoFixo
from app.models.custo_fixo_pagamento import CustoFixoPagamento
from app.models.custo_fixo_history import CustoFixoHistory
from app.services.audit_custos_fixos import log_change, serialize_custo_fixo


financeiro_bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")


# ---------------------------
# Helpers
# ---------------------------
def _clean_str(s: str | None) -> str:
    return (s or "").strip()


def _parse_decimal_ptbr(value: str) -> Decimal:
    """
    Aceita valores como:
      627,00
      1.234,56
      1234.56
    """
    if value is None:
        return Decimal("0.00")
    s = value.strip()
    if not s:
        return Decimal("0.00")
    s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _safe_due_date(year: int, month: int, day: int) -> date:
    """
    Se dia_pagamento for maior que o último dia do mês, usa o último dia do mês.
    Ex: 31 em abril -> 30/04
    """
    last_day = calendar.monthrange(year, month)[1]
    day = min(day, last_day)
    return date(year, month, day)


def _get_list_params_from_args():
    sort = _clean_str(request.args.get("sort")) or "agenda"
    view = _clean_str(request.args.get("view")) or "all"
    qtxt = _clean_str(request.args.get("q"))
    cat = _clean_str(request.args.get("cat")) or "all"
    ativo = _clean_str(request.args.get("ativo")) or "all"
    paid = _clean_str(request.args.get("paid")) or "all"
    return sort, view, qtxt, cat, ativo, paid


def _get_list_params_from_form():
    sort = _clean_str(request.form.get("sort")) or "agenda"
    view = _clean_str(request.form.get("view")) or "all"
    qtxt = _clean_str(request.form.get("q"))
    cat = _clean_str(request.form.get("cat")) or "all"
    ativo = _clean_str(request.form.get("ativo")) or "all"
    paid = _clean_str(request.form.get("paid")) or "all"
    return sort, view, qtxt, cat, ativo, paid


def _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid, anchor="#itens"):
    return redirect(
        url_for(
            "financeiro.custos_fixos",
            sort=sort,
            view=view,
            q=qtxt,
            cat=cat,
            ativo=ativo,
            paid=paid,
        )
        + (anchor or "")
    )


def _parse_form_fields_or_flash():
    nome = _clean_str(request.form.get("nome"))
    categoria = _clean_str(request.form.get("categoria")) or "Outros"
    valor_raw = request.form.get("valor_mensal") or "0"
    data_inicio_raw = request.form.get("data_inicio")  # yyyy-mm-dd
    data_fim_raw = _clean_str(request.form.get("data_fim")) or None

    dia_pagamento_raw = _clean_str(request.form.get("dia_pagamento"))
    dia_pagamento = None
    if dia_pagamento_raw:
        try:
            dia_pagamento = int(dia_pagamento_raw)
            if dia_pagamento < 1 or dia_pagamento > 31:
                raise ValueError()
        except Exception:
            return None, "Dia de pagamento inválido. Use um número de 1 a 31.", "danger"

    if not nome:
        return None, "Nome do custo é obrigatório.", "warning"

    try:
        valor = _parse_decimal_ptbr(valor_raw)
    except Exception:
        return None, "Valor inválido. Use formato como 627,00.", "danger"

    if not data_inicio_raw:
        return None, "Data de início é obrigatória.", "warning"

    return {
        "nome": nome,
        "categoria": categoria,
        "valor_mensal": valor,
        "dia_pagamento": dia_pagamento,
        "data_inicio": data_inicio_raw,
        "data_fim": data_fim_raw,
    }, None, None


# ---------------------------
# Página principal
# ---------------------------
@financeiro_bp.route("/custos-fixos", methods=["GET", "POST"])
@login_required
def custos_fixos():
    # ---------------------------
    # POST: criar custo fixo
    # ---------------------------
    if request.method == "POST":
        data, err, level = _parse_form_fields_or_flash()
        if err:
            flash(err, level)
            return redirect(url_for("financeiro.custos_fixos"))

        item = CustoFixo(
            user_id=current_user.id,
            nome=data["nome"],
            categoria=data["categoria"],
            valor_mensal=data["valor_mensal"],
            dia_pagamento=data["dia_pagamento"],
            data_inicio=data["data_inicio"],
            data_fim=data["data_fim"],
            ativo=True,
        )

        db.session.add(item)
        db.session.flush()  # <- garante item.id antes de auditar

        after = serialize_custo_fixo(item)
        log_change(
            item_id=item.id,
            action="create",
            user_id=current_user.id,
            before=None,
            after=after,
        )

        db.session.commit()
        flash("Custo fixo cadastrado.", "success")
        return redirect(url_for("financeiro.custos_fixos"))

    # ---------------------------
    # GET: params (sort/view + filtros)
    # ---------------------------
    sort, view, qtxt, cat, ativo, paid = _get_list_params_from_args()

    q = CustoFixo.query.filter_by(user_id=current_user.id)

    if qtxt:
        q = q.filter(CustoFixo.nome.ilike(f"%{qtxt}%"))

    if cat != "all":
        q = q.filter(CustoFixo.categoria == cat)

    if ativo == "active":
        q = q.filter(CustoFixo.ativo.is_(True))
    elif ativo == "inactive":
        q = q.filter(CustoFixo.ativo.is_(False))
    else:
        ativo = "all"

    # ordenação
    if sort == "nome":
        q = q.order_by(CustoFixo.ativo.desc(), CustoFixo.nome.asc())
    elif sort == "categoria":
        q = q.order_by(CustoFixo.ativo.desc(), CustoFixo.categoria.asc(), CustoFixo.nome.asc())
    elif sort == "valor_desc":
        q = q.order_by(CustoFixo.ativo.desc(), CustoFixo.valor_mensal.desc(), CustoFixo.nome.asc())
    elif sort == "valor_asc":
        q = q.order_by(CustoFixo.ativo.desc(), CustoFixo.valor_mensal.asc(), CustoFixo.nome.asc())
    elif sort == "inicio":
        q = q.order_by(CustoFixo.ativo.desc(), CustoFixo.data_inicio.desc(), CustoFixo.nome.asc())
    else:
        sort = "agenda"
        q = q.order_by(
            CustoFixo.ativo.desc(),
            CustoFixo.dia_pagamento.asc().nullslast(),
            CustoFixo.categoria.asc(),
            CustoFixo.nome.asc(),
        )

    itens_db = q.all()

    # ---------------------------
    # Pagos / Status do mês atual
    # ---------------------------
    hoje = date.today()
    ano_atual, mes_atual = hoje.year, hoje.month

    pagos = (
        CustoFixoPagamento.query
        .join(CustoFixo, CustoFixoPagamento.custo_fixo_id == CustoFixo.id)
        .filter(CustoFixo.user_id == current_user.id)
        .filter(CustoFixoPagamento.ano == ano_atual, CustoFixoPagamento.mes == mes_atual)
        .all()
    )
    pagos_map = {p.custo_fixo_id: p for p in pagos}

    def _status_do_item(item: CustoFixo):
        if not item.vigente_em(ano_atual, mes_atual):
            return ("Fora do mês", "bg-slate-100 text-slate-700")

        if pagos_map.get(item.id):
            return ("Pago", "bg-emerald-100 text-emerald-800")

        if not item.dia_pagamento:
            return ("Sem vencimento", "bg-slate-100 text-slate-700")

        vencimento = _safe_due_date(ano_atual, mes_atual, item.dia_pagamento)

        if hoje > vencimento:
            return ("Vencido", "bg-red-100 text-red-800")

        dias = (vencimento - hoje).days
        if dias == 0:
            return ("Vence hoje", "bg-orange-100 text-orange-900 border border-orange-200")
        if dias == 1:
            return ("Vence amanhã", "bg-orange-100 text-orange-900 border border-orange-200")
        if dias in (2, 3):
            return (f"Vence em {dias} dias", "bg-amber-100 text-amber-900")

        return (f"Vence dia {vencimento.day}", "bg-slate-100 text-slate-700")

    status_map = {i.id: _status_do_item(i) for i in itens_db}

    # ---------------------------
    # Totais do mês (vigentes)
    # ---------------------------
    total_vigente = Decimal("0.00")
    totais_por_categoria = defaultdict(lambda: Decimal("0.00"))

    for i in itens_db:
        if i.vigente_em(ano_atual, mes_atual):
            v = Decimal(str(i.valor_mensal))
            total_vigente += v
            totais_por_categoria[i.categoria] += v

    totais_ordenados = sorted(totais_por_categoria.items(), key=lambda x: x[1], reverse=True)

    # ---------------------------
    # Radar: próximos 7 dias / em aberto até fim do mês
    # ---------------------------
    total_proximos_7_dias = Decimal("0.00")
    total_em_aberto_mes = Decimal("0.00")

    fim_mes = calendar.monthrange(ano_atual, mes_atual)[1]
    last_day_date = date(ano_atual, mes_atual, fim_mes)

    for i in itens_db:
        if not i.vigente_em(ano_atual, mes_atual):
            continue
        if not i.dia_pagamento:
            continue
        if pagos_map.get(i.id):
            continue

        due = _safe_due_date(ano_atual, mes_atual, i.dia_pagamento)
        val = Decimal(str(i.valor_mensal))

        if hoje <= due <= (hoje + timedelta(days=7)):
            total_proximos_7_dias += val

        if hoje <= due <= last_day_date:
            total_em_aberto_mes += val

    # ---------------------------
    # Filtro paid em memória
    # ---------------------------
    itens_filtered = itens_db
    if paid == "paid":
        itens_filtered = [i for i in itens_filtered if i.vigente_em(ano_atual, mes_atual) and pagos_map.get(i.id)]
    elif paid == "unpaid":
        itens_filtered = [i for i in itens_filtered if i.vigente_em(ano_atual, mes_atual) and not pagos_map.get(i.id)]
    else:
        paid = "all"

    # ---------------------------
    # View
    # ---------------------------
    itens = itens_filtered
    if view == "next7":
        itens = [
            i for i in itens_filtered
            if i.vigente_em(ano_atual, mes_atual)
            and i.dia_pagamento
            and not pagos_map.get(i.id)
            and (hoje <= _safe_due_date(ano_atual, mes_atual, i.dia_pagamento) <= (hoje + timedelta(days=7)))
        ]
    elif view == "open_month":
        itens = [
            i for i in itens_filtered
            if i.vigente_em(ano_atual, mes_atual)
            and i.dia_pagamento
            and not pagos_map.get(i.id)
            and (hoje <= _safe_due_date(ano_atual, mes_atual, i.dia_pagamento) <= last_day_date)
        ]
    else:
        view = "all"

    categorias_db = sorted({i.categoria for i in itens_db if i.categoria})

    return render_template(
        "financeiro/custos_fixos.html",
        itens=itens,
        total_vigente=total_vigente,
        totais_por_categoria=totais_ordenados,
        ano=ano_atual,
        mes=mes_atual,
        sort=sort,
        view=view,
        status_map=status_map,
        total_proximos_7_dias=total_proximos_7_dias,
        total_em_aberto_mes=total_em_aberto_mes,
        q=qtxt,
        cat=cat,
        ativo=ativo,
        paid=paid,
        categorias_db=categorias_db,
    )


# ---------------------------
# API: histórico (JSON)
# ---------------------------
@financeiro_bp.route("/custos-fixos/<int:item_id>/history", methods=["GET"])
@login_required
def custos_fixos_history(item_id: int):
    CustoFixo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()

    rows = (
        CustoFixoHistory.query
        .filter(CustoFixoHistory.item_id == item_id)
        .order_by(CustoFixoHistory.changed_at.desc())
        .limit(100)
        .all()
    )

    return jsonify([
        {
            "id": r.id,
            "item_id": r.item_id,
            "action": r.action,
            "diff": r.diff,
            "snapshot": r.snapshot,
            "note": r.note,
            "changed_by": r.changed_by,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        }
        for r in rows
    ])


# ---------------------------
# Bulk actions
# ---------------------------
@financeiro_bp.route("/custos-fixos/bulk", methods=["POST"])
@login_required
def bulk_action_custos_fixos():
    action = _clean_str(request.form.get("action"))
    ids_raw = request.form.getlist("selected_ids")

    sort, view, qtxt, cat, ativo, paid = _get_list_params_from_form()

    def _back():
        return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)

    ids = []
    for x in ids_raw:
        try:
            ids.append(int(x))
        except Exception:
            pass

    if not ids:
        flash("Selecione pelo menos um item.", "warning")
        return _back()

    allowed = {"delete", "activate", "deactivate", "mark_paid", "unmark_paid"}
    if action not in allowed:
        flash("Ação inválida.", "danger")
        return _back()

    itens = (
        CustoFixo.query
        .filter(CustoFixo.user_id == current_user.id)
        .filter(CustoFixo.id.in_(ids))
        .all()
    )

    if not itens:
        flash("Nenhum item encontrado para aplicar a ação.", "warning")
        return _back()

    hoje = date.today()
    ano_atual, mes_atual = hoje.year, hoje.month

    pagamentos_existentes = (
        CustoFixoPagamento.query
        .filter(CustoFixoPagamento.ano == ano_atual, CustoFixoPagamento.mes == mes_atual)
        .filter(CustoFixoPagamento.custo_fixo_id.in_([i.id for i in itens]))
        .all()
    )
    pagos_map = {p.custo_fixo_id: p for p in pagamentos_existentes}

    if action == "delete":
        count = 0
        for i in itens:
            before = serialize_custo_fixo(i)
            if pagos_map.get(i.id):
                db.session.delete(pagos_map[i.id])
            db.session.delete(i)
            log_change(
                item_id=i.id,
                action="delete",
                user_id=current_user.id,
                before=before,
                after=None,
            )
            count += 1
        db.session.commit()
        flash(f"{count} item(ns) excluído(s).", "success")
        return _back()

    if action in ("activate", "deactivate"):
        new_value = (action == "activate")
        for i in itens:
            before = serialize_custo_fixo(i)
            i.ativo = new_value
            after = serialize_custo_fixo(i)
            log_change(
                item_id=i.id,
                action="bulk",
                user_id=current_user.id,
                before=before,
                after=after,
                note=action,
            )
        db.session.commit()
        flash(f"{len(itens)} item(ns) atualizado(s).", "success")
        return _back()

    if action == "mark_paid":
        created = 0
        skipped = 0
        for i in itens:
            if not i.vigente_em(ano_atual, mes_atual):
                skipped += 1
                continue
            if pagos_map.get(i.id):
                continue
            p = CustoFixoPagamento(custo_fixo_id=i.id, ano=ano_atual, mes=mes_atual)
            db.session.add(p)
            created += 1
            log_change(
                item_id=i.id,
                action="toggle_paid",
                user_id=current_user.id,
                before={"paid": False, "ano": ano_atual, "mes": mes_atual},
                after={"paid": True, "ano": ano_atual, "mes": mes_atual},
                note="bulk mark_paid",
            )
        db.session.commit()
        if skipped:
            flash(f"Marcado(s) como pago: {created}. Ignorado(s) (fora do mês): {skipped}.", "success")
        else:
            flash(f"Marcado(s) como pago: {created}.", "success")
        return _back()

    if action == "unmark_paid":
        removed = 0
        for i in itens:
            p = pagos_map.get(i.id)
            if not p:
                continue
            db.session.delete(p)
            removed += 1
            log_change(
                item_id=i.id,
                action="toggle_paid",
                user_id=current_user.id,
                before={"paid": True, "ano": ano_atual, "mes": mes_atual},
                after={"paid": False, "ano": ano_atual, "mes": mes_atual},
                note="bulk unmark_paid",
            )
        db.session.commit()
        flash(f"Pagamento(s) desmarcado(s): {removed}.", "success")
        return _back()

    flash("Nada a fazer.", "info")
    return _back()


# ---------------------------
# Update
# ---------------------------
@financeiro_bp.route("/custos-fixos/<int:item_id>/update", methods=["POST"])
@login_required
def update_custo_fixo(item_id: int):
    item = CustoFixo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    sort, view, qtxt, cat, ativo, paid = _get_list_params_from_args()

    data, err, level = _parse_form_fields_or_flash()
    if err:
        flash(err, level)
        return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)

    before = serialize_custo_fixo(item)
    item.nome = data["nome"]
    item.categoria = data["categoria"]
    item.valor_mensal = data["valor_mensal"]
    item.dia_pagamento = data["dia_pagamento"]
    item.data_inicio = data["data_inicio"]
    item.data_fim = data["data_fim"]
    after = serialize_custo_fixo(item)

    log_change(item_id=item.id, action="update", user_id=current_user.id, before=before, after=after)
    db.session.commit()
    flash("Custo fixo atualizado.", "success")
    return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)


# ---------------------------
# Toggle ativo
# ---------------------------
@financeiro_bp.route("/custos-fixos/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_custo_fixo(item_id: int):
    item = CustoFixo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    sort, view, qtxt, cat, ativo, paid = _get_list_params_from_args()

    before = serialize_custo_fixo(item)
    item.ativo = not item.ativo
    after = serialize_custo_fixo(item)

    log_change(item_id=item.id, action="toggle_active", user_id=current_user.id, before=before, after=after)
    db.session.commit()
    flash("Status atualizado.", "success")
    return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)


# ---------------------------
# Delete
# ---------------------------
@financeiro_bp.route("/custos-fixos/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_custo_fixo(item_id: int):
    item = CustoFixo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    sort, view, qtxt, cat, ativo, paid = _get_list_params_from_args()

    before = serialize_custo_fixo(item)
    hoje = date.today()
    ano_atual, mes_atual = hoje.year, hoje.month
    p = CustoFixoPagamento.query.filter_by(custo_fixo_id=item.id, ano=ano_atual, mes=mes_atual).first()
    if p:
        db.session.delete(p)
    db.session.delete(item)

    log_change(item_id=item.id, action="delete", user_id=current_user.id, before=before, after=None)
    db.session.commit()
    flash("Custo fixo removido.", "success")
    return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)


# ---------------------------
# Toggle pago (mês atual)
# ---------------------------
@financeiro_bp.route("/custos-fixos/<int:item_id>/pago", methods=["POST"])
@login_required
def toggle_pago_custo_fixo(item_id: int):
    item = CustoFixo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    sort, view, qtxt, cat, ativo, paid = _get_list_params_from_args()

    hoje = date.today()
    ano_atual, mes_atual = hoje.year, hoje.month

    if not item.vigente_em(ano_atual, mes_atual):
        flash("Este custo não está vigente no mês atual.", "warning")
        return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)

    pagamento = CustoFixoPagamento.query.filter_by(
        custo_fixo_id=item.id, ano=ano_atual, mes=mes_atual
    ).first()
    was_paid = bool(pagamento)

    if pagamento:
        db.session.delete(pagamento)
        flash("Pagamento removido (desmarcado).", "success")
    else:
        pagamento = CustoFixoPagamento(custo_fixo_id=item.id, ano=ano_atual, mes=mes_atual)
        db.session.add(pagamento)
        flash("Marcado como pago no mês atual.", "success")

    log_change(
        item_id=item.id,
        action="toggle_paid",
        user_id=current_user.id,
        before={"paid": was_paid, "ano": ano_atual, "mes": mes_atual},
        after={"paid": (not was_paid), "ano": ano_atual, "mes": mes_atual},
    )
    db.session.commit()
    return _redirect_back_to_list(sort, view, qtxt, cat, ativo, paid)
