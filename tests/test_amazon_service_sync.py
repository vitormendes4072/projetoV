"""
Testes unitários para as três funções de sync em app/integrations/amazon/service.py:
  - sync_orders_and_items
  - sync_financial_events
  - upsert_inventory_snapshots

Nenhuma chamada real à SP-API nem ao banco de dados.
  - list_orders / list_order_items / list_financial_events são mockados no namespace
    do módulo service.py (são nomes de função module-level).
  - `db` é mockado via patch("app.db"): as funções fazem `from app import db` de
    forma lazy (dentro do corpo), então em runtime resolvem app.db — que é o mock.
  - `pg_insert` (PostgreSQL-specific) é mockado via patch no módulo sqlalchemy.
  - Modelos SQLAlchemy (AmazonOrder etc.) são instanciados normalmente — sem sessão
    ativa, SQLAlchemy só popula atributos Python puros.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from app.integrations.amazon.service import (
    sync_orders_and_items,
    sync_financial_events,
    upsert_inventory_snapshots,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_SERVICE_ORDERS   = "app.integrations.amazon.service.orders"
_SERVICE_FINANCES = "app.integrations.amazon.service.finances"
_PG_INSERT = "sqlalchemy.dialects.postgresql.insert"
_MARKETPLACE = "A2Q3Y263D00KWC"


# ---------------------------------------------------------------------------
# Factories de dados
# ---------------------------------------------------------------------------

def _fake_conn(marketplace_id=_MARKETPLACE):
    c = MagicMock()
    c.marketplace_id = marketplace_id
    return c


def _order_api(order_id="111-2222-3333", status="Shipped",
               total="100.00", currency="BRL"):
    """Payload de um pedido como retornado pela Orders API."""
    return {
        "AmazonOrderId": order_id,
        "OrderStatus": status,
        "PurchaseDate": "2026-01-15T10:00:00Z",
        "OrderTotal": {"Amount": total, "CurrencyCode": currency},
    }


def _item_api(sku="SKU-A", asin="B001TEST", qty=2, price="50.00", currency="BRL"):
    """Payload de um item de pedido como retornado pela Orders API."""
    return {
        "SellerSKU": sku,
        "ASIN": asin,
        "QuantityOrdered": qty,
        "ItemPrice": {"Amount": price, "CurrencyCode": currency},
    }


def _financial_event(order_id="111-2222-3333",
                     posted="2026-01-15T00:00:00Z",
                     amount="50.00", currency="BRL", sku="SKU-A"):
    """Payload de um evento financeiro como retornado pela Finances API."""
    return {
        "AmazonOrderId": order_id,
        "PostedDate": posted,
        "Amount": {"Amount": amount, "CurrencyCode": currency},
        "SellerSKU": sku,
    }


def _inventory(sku="SKU-A", asin="B001TEST", total=10,
               reserved=2, working=1, shipped=1, receiving=0):
    """Payload de um inventory summary como retornado pela Inventories API."""
    return {
        "sellerSku": sku,
        "asin": asin,
        "totalQuantity": total,
        "inventoryDetails": {
            "reservedQuantity": reserved,
            "inboundWorkingQuantity": working,
            "inboundShippedQuantity": shipped,
            "inboundReceivingQuantity": receiving,
        },
    }


# ---------------------------------------------------------------------------
# sync_orders_and_items
# ---------------------------------------------------------------------------

class TestSyncOrdersAndItems:
    """
    Testa sync_orders_and_items isolando list_orders, list_order_items e app.db.
    Contrato: retorna (orders_upserted, items_inserted, orders_returned_by_api).
    Não faz commit — responsabilidade do chamador.
    """

    def _run(self, api_orders, items_fn=None, scalar_rv=None, user_id=1):
        """
        Executa sync_orders_and_items com dependências mockadas.
        items_fn: callable(conn, order_id) -> list, ou None para retornar [].
        scalar_rv: valor retornado por db.session.scalar (None = novo pedido).
        """
        mock_db = MagicMock()
        mock_db.session.scalar.return_value = scalar_rv
        mock_db.session.execute.return_value = MagicMock()

        items_side_effect = items_fn if items_fn is not None else (lambda *_: [])

        with patch("app.db", mock_db), \
             patch(f"{_SERVICE_ORDERS}.list_orders", return_value=api_orders), \
             patch(f"{_SERVICE_ORDERS}.list_order_items", side_effect=items_side_effect):
            result = sync_orders_and_items(
                _fake_conn(), user_id=user_id, created_after_iso="2026-01-01T00:00:00Z"
            )

        return result, mock_db

    # --- Lista vazia ---

    def test_empty_orders_list_returns_zeros(self):
        (upserted, items, total), _ = self._run([])
        assert upserted == 0
        assert items == 0
        assert total == 0

    # --- Filtragem de registros inválidos ---

    def test_order_without_amazon_order_id_is_skipped(self):
        bad = {"OrderStatus": "Shipped"}  # sem AmazonOrderId
        (upserted, items, total), mock_db = self._run([bad])
        assert upserted == 0
        assert items == 0
        assert total == 1            # contado em orders_returned_by_api
        mock_db.session.add.assert_not_called()

    # --- Criação e atualização ---

    def test_creates_new_order_when_not_in_db(self):
        (upserted, _, total), mock_db = self._run(
            [_order_api("111-NEW")], scalar_rv=None
        )
        assert upserted == 1
        assert total == 1
        mock_db.session.add.assert_called()

    def test_updates_existing_order_in_db(self):
        existing = MagicMock()
        (upserted, _, _), mock_db = self._run(
            [_order_api("111-EXIST")], scalar_rv=existing
        )
        assert upserted == 1
        # O objeto existente deve ser re-adicionado à sessão (upsert)
        mock_db.session.add.assert_called_with(existing)

    # --- Campos mapeados corretamente ---

    def test_order_status_currency_amount_set_on_existing_row(self):
        existing = MagicMock()
        self._run(
            [_order_api("111-F", status="Pending", total="123.45", currency="BRL")],
            scalar_rv=existing,
        )
        assert existing.order_status == "Pending"
        assert existing.currency == "BRL"
        assert existing.order_total_amount == "123.45"

    def test_order_raw_json_is_stored(self):
        existing = MagicMock()
        order_data = _order_api("111-RAW")
        self._run([order_data], scalar_rv=existing)
        assert existing.raw_json == order_data

    # --- Itens de pedido ---

    def test_items_are_inserted_for_order(self):
        items = [_item_api("SKU-A"), _item_api("SKU-B")]
        (upserted, inserted_items, _), _ = self._run(
            [_order_api("111-ITEMS")], items_fn=lambda *_: items
        )
        assert upserted == 1
        assert inserted_items == 2

    def test_existing_items_are_deleted_before_reinsertion(self):
        """db.session.execute deve ser chamado para o DELETE antes de inserir itens."""
        (_, _, _), mock_db = self._run(
            [_order_api("111-DEL")], items_fn=lambda *_: [_item_api()]
        )
        mock_db.session.execute.assert_called()

    def test_items_fetch_failure_does_not_abort_order_upsert(self):
        """Se list_order_items lança, o pedido ainda é salvo e a iteração continua."""
        def _raise(*_):
            raise RuntimeError("SP-API timeout")

        (upserted, inserted_items, _), mock_db = self._run(
            [_order_api("111-FAIL")], items_fn=_raise
        )
        assert upserted == 1        # pedido salvo
        assert inserted_items == 0  # itens: nenhum (erro tratado com continue)
        mock_db.session.add.assert_called()

    # --- Múltiplos pedidos ---

    def test_multiple_orders_cumulate_counts(self):
        orders = [_order_api("111-A"), _order_api("111-B")]
        items_per_order = [_item_api("SKU-X"), _item_api("SKU-Y")]
        (upserted, inserted_items, total), _ = self._run(
            orders, items_fn=lambda *_: items_per_order
        )
        assert upserted == 2
        assert inserted_items == 4   # 2 itens × 2 pedidos
        assert total == 2

    def test_one_order_fails_items_others_still_processed(self):
        """Falha no fetch de itens do pedido 1 não impede o pedido 2."""
        orders = [_order_api("111-BAD"), _order_api("111-GOOD")]
        call_count = {"n": 0}

        def _items_fn(*_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("falha no 1o pedido")
            return [_item_api("SKU-OK")]

        (upserted, inserted_items, total), _ = self._run(orders, items_fn=_items_fn)
        assert upserted == 2        # ambos os pedidos salvos
        assert inserted_items == 1  # só itens do 2o pedido
        assert total == 2


# ---------------------------------------------------------------------------
# sync_financial_events
# ---------------------------------------------------------------------------

class TestSyncFinancialEvents:
    """
    Testa sync_financial_events isolando list_financial_events, pg_insert e app.db.
    Contrato: retorna int (total de eventos inseridos). Não faz commit.
    """

    def _run(self, events_dict, rowcount=1, user_id=1):
        """
        Executa sync_financial_events com dependências mockadas.
        rowcount: valor simulado de result.rowcount após execute (1=inserido, 0=conflict).
        """
        mock_db = MagicMock()
        exec_result = MagicMock()
        exec_result.rowcount = rowcount
        mock_db.session.execute.return_value = exec_result

        # pg_insert retorna uma cadeia de mocks: .values().on_conflict_do_nothing()
        mock_pg_insert = MagicMock()
        (mock_pg_insert.return_value
         .values.return_value
         .on_conflict_do_nothing.return_value) = MagicMock()

        with patch("app.db", mock_db), \
             patch(_PG_INSERT, mock_pg_insert), \
             patch(f"{_SERVICE_FINANCES}.list_financial_events",
                   return_value=(events_dict, {})):
            inserted = sync_financial_events(
                _fake_conn(), user_id=user_id, posted_after_iso="2026-01-01T00:00:00Z"
            )

        return inserted, mock_db, mock_pg_insert

    # --- Sem eventos ---

    def test_empty_events_dict_returns_zero(self):
        inserted, _, _ = self._run({})
        assert inserted == 0

    def test_empty_event_list_returns_zero(self):
        inserted, mock_db, _ = self._run({"ShipmentEventList": []})
        assert inserted == 0
        mock_db.session.execute.assert_not_called()

    # --- Inserção básica ---

    def test_inserts_single_shipment_event(self):
        ev = _financial_event("111-S1")
        inserted, mock_db, _ = self._run({"ShipmentEventList": [ev]}, rowcount=1)
        assert inserted == 1
        mock_db.session.execute.assert_called_once()

    def test_pg_insert_called_with_financial_event_model(self):
        from app.models.amazon_finances import AmazonFinancialEvent
        ev = _financial_event("111-M1")
        _, _, mock_pg_insert = self._run({"ShipmentEventList": [ev]}, rowcount=1)
        mock_pg_insert.assert_called_once_with(AmazonFinancialEvent)

    # --- Dedupe in-memory ---

    def test_identical_events_in_same_run_deduped_in_memory(self):
        """Mesmo dict de evento duas vezes na lista → só 1 insert tentado."""
        ev = _financial_event("111-DUP")
        inserted, mock_db, _ = self._run({"ShipmentEventList": [ev, ev]}, rowcount=1)
        assert inserted == 1
        mock_db.session.execute.assert_called_once()

    def test_events_with_different_order_ids_are_both_inserted(self):
        evs = [_financial_event("111-A"), _financial_event("111-B")]
        inserted, mock_db, _ = self._run({"ShipmentEventList": evs}, rowcount=1)
        assert inserted == 2
        assert mock_db.session.execute.call_count == 2

    # --- ON CONFLICT DO NOTHING ---

    def test_rowcount_zero_not_counted_as_inserted(self):
        """rowcount=0 significa ON CONFLICT DO NOTHING — evento já existia."""
        ev = _financial_event("111-CONFLICT")
        inserted, _, _ = self._run({"ShipmentEventList": [ev]}, rowcount=0)
        assert inserted == 0

    # --- Tipos de evento variados ---

    def test_non_list_event_type_is_skipped(self):
        events = {
            "ShipmentEventList": [_financial_event("111-VALID")],
            "SomeScalarKey": "não é lista",
            "AnotherScalar": 42,
        }
        inserted, mock_db, _ = self._run(events, rowcount=1)
        assert inserted == 1            # só ShipmentEventList inserido
        mock_db.session.execute.assert_called_once()

    def test_multiple_event_types_counted_independently(self):
        events = {
            "ShipmentEventList": [_financial_event("111-S1"), _financial_event("111-S2")],
            "RefundEventList":   [_financial_event("111-R1")],
        }
        inserted, mock_db, _ = self._run(events, rowcount=1)
        assert inserted == 3
        assert mock_db.session.execute.call_count == 3

    # --- Evento não-dict ---

    def test_non_dict_event_wrapped_and_inserted(self):
        """Evento que não é dict é encapsulado em {'value': ev} antes do insert."""
        events = {"AdjustmentEventList": ["raw_string_event"]}
        inserted, mock_db, _ = self._run(events, rowcount=1)
        assert inserted == 1
        mock_db.session.execute.assert_called_once()

    # --- Fingerprint garante unicidade entre usuários ---

    def test_same_event_different_users_both_inserted(self):
        """O fingerprint inclui user_id, então o mesmo evento de dois users é distinto."""
        ev = _financial_event("111-SAME")
        events = {"ShipmentEventList": [ev]}

        inserted_u1, _, _ = self._run(events, rowcount=1, user_id=1)
        inserted_u2, _, _ = self._run(events, rowcount=1, user_id=2)

        assert inserted_u1 == 1
        assert inserted_u2 == 1


# ---------------------------------------------------------------------------
# upsert_inventory_snapshots
# ---------------------------------------------------------------------------

class TestUpsertInventorySnapshots:
    """
    Testa upsert_inventory_snapshots isolando app.db.
    Contrato: retorna (inserted, updated). Não faz commit.
    """

    def _run(self, summaries, scalar_rv=None, user_id=1, marketplace_id=_MARKETPLACE):
        mock_db = MagicMock()
        mock_db.session.scalar.return_value = scalar_rv

        with patch("app.db", mock_db):
            result = upsert_inventory_snapshots(user_id, marketplace_id, summaries)

        return result, mock_db

    # --- Lista vazia ---

    def test_empty_list_returns_zeros(self):
        (inserted, updated), _ = self._run([])
        assert inserted == 0
        assert updated == 0

    # --- Filtragem sem SKU ---

    def test_item_without_sku_is_skipped(self):
        bad = {"asin": "B001TEST", "totalQuantity": 5}  # sem sellerSku
        (inserted, updated), mock_db = self._run([bad])
        assert inserted == 0
        assert updated == 0
        mock_db.session.add.assert_not_called()

    # --- Inserção e atualização ---

    def test_inserts_new_snapshot_when_not_in_db(self):
        (inserted, updated), mock_db = self._run([_inventory("SKU-NEW")], scalar_rv=None)
        assert inserted == 1
        assert updated == 0
        mock_db.session.add.assert_called_once()

    def test_updates_existing_snapshot(self):
        existing = MagicMock()
        (inserted, updated), mock_db = self._run([_inventory("SKU-E")], scalar_rv=existing)
        assert inserted == 0
        assert updated == 1
        mock_db.session.add.assert_called_once_with(existing)

    # --- Mapeamento de quantidades ---

    def test_all_quantities_set_correctly_on_new_snapshot(self):
        s = _inventory("SKU-QTY", total=10, reserved=2, working=3, shipped=4, receiving=1)
        _, mock_db = self._run([s], scalar_rv=None)
        added = mock_db.session.add.call_args[0][0]
        assert added.fulfillable_qty == 10
        assert added.reserved_qty == 2
        assert added.inbound_working_qty == 3
        assert added.inbound_shipped_qty == 4
        assert added.inbound_receiving_qty == 1

    def test_asin_set_on_snapshot(self):
        s = _inventory("SKU-ASIN", asin="B009TEST")
        _, mock_db = self._run([s], scalar_rv=None)
        added = mock_db.session.add.call_args[0][0]
        assert added.asin == "B009TEST"

    def test_missing_qty_fields_default_to_zero(self):
        s = {"sellerSku": "SKU-ZERO"}   # sem campos de quantidade
        _, mock_db = self._run([s], scalar_rv=None)
        added = mock_db.session.add.call_args[0][0]
        assert added.fulfillable_qty == 0
        assert added.reserved_qty == 0
        assert added.inbound_working_qty == 0

    # --- Aliases de chave ---

    def test_accepts_seller_sku_uppercase_key(self):
        s = {"SellerSKU": "SKU-UP1", "totalQuantity": 5}
        (inserted, _), _ = self._run([s], scalar_rv=None)
        assert inserted == 1

    def test_accepts_seller_sku_mixed_case_key(self):
        s = {"sellerSKU": "SKU-MIX", "totalQuantity": 3}
        (inserted, _), _ = self._run([s])
        assert inserted == 1

    def test_accepts_total_quantity_uppercase_key(self):
        s = {"sellerSku": "SKU-TQUP", "TotalQuantity": 7}
        _, mock_db = self._run([s], scalar_rv=None)
        added = mock_db.session.add.call_args[0][0]
        assert added.fulfillable_qty == 7

    # --- Múltiplos SKUs ---

    def test_multiple_skus_mixed_insert_and_update(self):
        existing = MagicMock()
        mock_db = MagicMock()
        # Dois novos (scalar=None) e um existente
        mock_db.session.scalar.side_effect = [None, None, existing]

        with patch("app.db", mock_db):
            inserted, updated = upsert_inventory_snapshots(
                1, _MARKETPLACE,
                [_inventory("SKU-N1"), _inventory("SKU-N2"), _inventory("SKU-E1")]
            )

        assert inserted == 2
        assert updated == 1
        assert mock_db.session.add.call_count == 3

    def test_skips_missing_sku_mid_list_and_continues(self):
        """Item sem SKU no meio da lista não interrompe o processamento dos demais."""
        summaries = [
            _inventory("SKU-BEFORE"),
            {"asin": "B001NOSKU"},          # sem SKU — deve ser pulado
            _inventory("SKU-AFTER"),
        ]
        (inserted, updated), mock_db = self._run(summaries, scalar_rv=None)
        assert inserted == 2    # SKU-BEFORE e SKU-AFTER
        assert updated == 0
        assert mock_db.session.add.call_count == 2
