from datetime import datetime, timezone

def financial_events_mock(order_id: str):
    now = datetime.now(timezone.utc).isoformat()

    return {
        "ShipmentEventList": [
            {
                "AmazonOrderId": order_id,
                "PostedDate": now,
                "ShipmentItemList": [
                    # SKU 1 (qty 1)
                    {
                        "SellerSKU": "SKU-TESTE-001",
                        "QuantityShipped": 1,
                        "ItemChargeList": [
                            {"ChargeType": "Principal", "ChargeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": 89.90}},
                        ],
                        "ItemFeeList": [
                            {"FeeType": "Commission", "FeeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": -11.69}},
                            {"FeeType": "FBAPerUnitFulfillmentFee", "FeeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": -0.00}},
                        ],
                    },

                    # SKU 2 (qty 2)
                    {
                        "SellerSKU": "SKU-TESTE-002",
                        "QuantityShipped": 2,
                        "ItemChargeList": [
                            {"ChargeType": "Principal", "ChargeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": 59.90}},
                        ],
                        "ItemFeeList": [
                            {"FeeType": "Commission", "FeeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": -7.79}},
                            {"FeeType": "FBAPerUnitFulfillmentFee", "FeeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": -0.00}},
                        ],
                    },
                ],
            }
        ],

        # Exemplo de taxa não atrelada a pedido (opcional)
        "ServiceFeeEventList": [
            {
                "PostedDate": now,
                "FeeReason": "SubscriptionFee",
                "FeeAmount": {"CurrencyCode": "BRL", "CurrencyAmount": -39.00},
            }
        ],
    }
