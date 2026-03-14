from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import OpportunityType


@dataclass
class BrokerConfig:
    meritz_base_url: str = "https://openapi.meritzsec.co.kr"
    binance_base_url: str = "https://api.binance.com"
    request_timeout_s: int = 10
    max_retries: int = 2
    recv_window_ms: int = 5000


@dataclass
class ValidationAdjustment:
    field: str
    old: float
    new: float
    reason: str


@dataclass
class ValidationResult:
    valid: bool
    blocked_reason: str = ""
    corrected: bool = False
    normalized_price: float = 0.0
    normalized_quantity: float = 0.0
    normalized_notional: float = 0.0
    adjustments: list[ValidationAdjustment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "blocked_reason": self.blocked_reason,
            "corrected": self.corrected,
            "normalized_price": self.normalized_price,
            "normalized_quantity": self.normalized_quantity,
            "normalized_notional": self.normalized_notional,
            "adjustments": [asdict(adj) for adj in self.adjustments],
        }


@dataclass
class SymbolRules:
    tick_size: float
    step_size: float
    min_qty: float
    min_notional: float
    price_precision: int | None = None
    quantity_precision: int | None = None


class OrderValidationEngine:
    @staticmethod
    def _round_down(value: float, step: float) -> float:
        if step <= 0:
            return value
        d_value = Decimal(str(value))
        d_step = Decimal(str(step))
        rounded = (d_value / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
        return float(rounded)

    @staticmethod
    def _apply_precision(value: float, precision: int | None) -> float:
        if precision is None:
            return value
        quant = Decimal("1").scaleb(-precision)
        return float(Decimal(str(value)).quantize(quant, rounding=ROUND_DOWN))

    @classmethod
    def normalize_price(cls, price: float, rules: SymbolRules) -> tuple[float, list[ValidationAdjustment]]:
        adjustments: list[ValidationAdjustment] = []
        normalized = cls._round_down(price, rules.tick_size)
        normalized = cls._apply_precision(normalized, rules.price_precision)
        if normalized != price:
            adjustments.append(ValidationAdjustment(field="price", old=price, new=normalized, reason="tick/precision"))
        return normalized, adjustments

    @classmethod
    def normalize_quantity(cls, quantity: float, rules: SymbolRules) -> tuple[float, list[ValidationAdjustment]]:
        adjustments: list[ValidationAdjustment] = []
        normalized = cls._round_down(quantity, rules.step_size)
        normalized = cls._apply_precision(normalized, rules.quantity_precision)
        if normalized != quantity:
            adjustments.append(
                ValidationAdjustment(field="quantity", old=quantity, new=normalized, reason="step/precision")
            )
        return normalized, adjustments

    @classmethod
    def validate_order(
        cls,
        *,
        quantity: float,
        price: float,
        rules: SymbolRules,
        auto_correct: bool = True,
    ) -> ValidationResult:
        if quantity <= 0 or price <= 0:
            return ValidationResult(valid=False, blocked_reason="quantity and price must be positive")

        normalized_price = price
        normalized_quantity = quantity
        adjustments: list[ValidationAdjustment] = []

        if auto_correct:
            normalized_price, adj_price = cls.normalize_price(normalized_price, rules)
            normalized_quantity, adj_qty = cls.normalize_quantity(normalized_quantity, rules)
            adjustments.extend(adj_price)
            adjustments.extend(adj_qty)

        if normalized_quantity <= 0:
            return ValidationResult(valid=False, blocked_reason="quantity became zero after normalization")

        if normalized_quantity < rules.min_qty:
            return ValidationResult(
                valid=False,
                blocked_reason=(
                    f"quantity below minQty: {normalized_quantity:.12f} < {rules.min_qty:.12f}"
                ),
                corrected=bool(adjustments),
                normalized_price=normalized_price,
                normalized_quantity=normalized_quantity,
                normalized_notional=normalized_price * normalized_quantity,
                adjustments=adjustments,
            )

        notional = normalized_price * normalized_quantity
        if notional < rules.min_notional:
            return ValidationResult(
                valid=False,
                blocked_reason=f"notional below minNotional: {notional:.8f} < {rules.min_notional:.8f}",
                corrected=bool(adjustments),
                normalized_price=normalized_price,
                normalized_quantity=normalized_quantity,
                normalized_notional=notional,
                adjustments=adjustments,
            )

        return ValidationResult(
            valid=True,
            corrected=bool(adjustments),
            normalized_price=normalized_price,
            normalized_quantity=normalized_quantity,
            normalized_notional=notional,
            adjustments=adjustments,
        )


@dataclass
class OrderResult:
    broker: str
    market: OpportunityType
    symbol: str
    side: str
    budget: float
    status: str
    order_id: str
    client_order_id: str
    raw: str
    validation: dict[str, Any] | None = None


class _RetryHTTPMixin:
    def _request_json(self, req: Request, timeout_s: int, max_retries: int) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                with urlopen(req, timeout=timeout_s) as resp:
                    body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
            except (HTTPError, URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(0.3 * (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP request failed after retries: {exc}") from exc
        raise RuntimeError(f"Unexpected request state: {last_error}")


class MeritzBroker(_RetryHTTPMixin):
    """메리츠증권 API 어댑터."""

    def __init__(self, config: BrokerConfig | None = None) -> None:
        self.config = config or BrokerConfig()
        self.api_key = os.getenv("MERITZ_API_KEY", "")
        self.api_secret = os.getenv("MERITZ_API_SECRET", "")
        self.account_no = os.getenv("MERITZ_ACCOUNT_NO", "")

    def _live_enabled(self) -> bool:
        return bool(self.api_key and self.api_secret and self.account_no)

    def _signature(self, payload: str, timestamp_ms: int) -> str:
        msg = f"{timestamp_ms}.{payload}".encode("utf-8")
        return hmac.new(self.api_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    def place_order(self, symbol: str, budget: float, side: str = "buy", client_order_id: str | None = None) -> OrderResult:
        cid = client_order_id or f"meritz-{uuid.uuid4().hex[:18]}"
        if not self._live_enabled():
            return OrderResult(
                broker="meritz",
                market=OpportunityType.STOCK,
                symbol=symbol,
                side=side,
                budget=budget,
                status="stub_submitted",
                order_id=f"stub-{cid}",
                client_order_id=cid,
                raw=f"meritz_stub order side={side} symbol={symbol} budget={budget:.2f}",
            )

        payload = {
            "accountNo": self.account_no,
            "symbol": symbol,
            "side": side,
            "budget": budget,
            "orderType": "market",
            "clientOrderId": cid,
        }
        body = json.dumps(payload)
        ts = int(time.time() * 1000)
        req = Request(
            f"{self.config.meritz_base_url}/v1/orders",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "X-API-TIMESTAMP": str(ts),
                "X-API-SIGNATURE": self._signature(body, ts),
            },
            method="POST",
        )
        data = self._request_json(req, self.config.request_timeout_s, self.config.max_retries)
        order_id = data.get("orderId", "unknown")
        status = data.get("status", "submitted")
        return OrderResult(
            broker="meritz",
            market=OpportunityType.STOCK,
            symbol=symbol,
            side=side,
            budget=budget,
            status=status,
            order_id=str(order_id),
            client_order_id=cid,
            raw=json.dumps(data, ensure_ascii=False),
        )

    def get_order(self, order_id: str) -> dict[str, Any]:
        if not self._live_enabled():
            return {"orderId": order_id, "status": "FILLED", "stub": True}
        req = Request(
            f"{self.config.meritz_base_url}/v1/orders/{order_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        return self._request_json(req, self.config.request_timeout_s, self.config.max_retries)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        if not self._live_enabled():
            return {"orderId": order_id, "status": "CANCELED", "stub": True}
        req = Request(
            f"{self.config.meritz_base_url}/v1/orders/{order_id}/cancel",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        return self._request_json(req, self.config.request_timeout_s, self.config.max_retries)


class BinanceBroker(_RetryHTTPMixin):
    def __init__(
        self,
        config: BrokerConfig | None = None,
        symbol_rules_overrides: dict[str, SymbolRules] | None = None,
        stub_reference_price: float = 100.0,
    ) -> None:
        self.config = config or BrokerConfig()
        self.api_key = os.getenv("BINANCE_API_KEY", "")
        self.api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.stub_reference_price = stub_reference_price
        self.symbol_rules_overrides = symbol_rules_overrides or {}
        self._symbol_rules_cache: dict[str, SymbolRules] = {}

    def _live_enabled(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params)
        return hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _signed_request(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        signed = dict(params)
        signed["timestamp"] = int(time.time() * 1000)
        signed["recvWindow"] = self.config.recv_window_ms
        signed["signature"] = self._sign(signed)
        query = urlencode(signed)
        req = Request(
            f"{self.config.binance_base_url}{path}?{query}",
            headers={"X-MBX-APIKEY": self.api_key},
            method=method,
        )
        return self._request_json(req, self.config.request_timeout_s, self.config.max_retries)

    def _fetch_symbol_rules_live(self, symbol: str) -> SymbolRules:
        req = Request(
            f"{self.config.binance_base_url}/api/v3/exchangeInfo?symbol={symbol}",
            method="GET",
        )
        data = self._request_json(req, self.config.request_timeout_s, self.config.max_retries)
        symbols = data.get("symbols", [])
        if not symbols:
            raise RuntimeError(f"symbol rules not found for {symbol}")
        item = symbols[0]
        filters = {f.get("filterType"): f for f in item.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_filter = filters.get("LOT_SIZE", {})
        min_notional_filter = filters.get("MIN_NOTIONAL", {})
        return SymbolRules(
            tick_size=float(price_filter.get("tickSize", 0.01)),
            step_size=float(lot_filter.get("stepSize", 0.0001)),
            min_qty=float(lot_filter.get("minQty", 0.0001)),
            min_notional=float(min_notional_filter.get("minNotional", 5.0)),
            price_precision=item.get("quotePrecision"),
            quantity_precision=item.get("baseAssetPrecision"),
        )

    def _default_stub_rules(self, symbol: str) -> SymbolRules:
        return SymbolRules(
            tick_size=0.01,
            step_size=0.0001,
            min_qty=0.0001,
            min_notional=5.0,
            price_precision=2,
            quantity_precision=6,
        )

    def get_symbol_rules(self, symbol: str) -> SymbolRules:
        normalized = symbol.replace("-", "")
        if normalized in self.symbol_rules_overrides:
            return self.symbol_rules_overrides[normalized]
        if normalized in self._symbol_rules_cache:
            return self._symbol_rules_cache[normalized]
        rules = self._fetch_symbol_rules_live(normalized) if self._live_enabled() else self._default_stub_rules(normalized)
        self._symbol_rules_cache[normalized] = rules
        return rules

    def _get_reference_price(self, symbol: str) -> float:
        if not self._live_enabled():
            return self.stub_reference_price
        req = Request(
            f"{self.config.binance_base_url}/api/v3/ticker/price?symbol={symbol}",
            method="GET",
        )
        data = self._request_json(req, self.config.request_timeout_s, self.config.max_retries)
        return float(data.get("price", self.stub_reference_price))

    def _validate_order(self, symbol: str, budget: float) -> ValidationResult:
        rules = self.get_symbol_rules(symbol)
        reference_price = self._get_reference_price(symbol)
        quantity = budget / reference_price if reference_price > 0 else 0.0
        return OrderValidationEngine.validate_order(quantity=quantity, price=reference_price, rules=rules, auto_correct=True)

    def place_order(self, symbol: str, budget: float, side: str = "BUY", client_order_id: str | None = None) -> OrderResult:
        normalized_symbol = symbol.replace("-", "")
        cid = client_order_id or f"binance-{uuid.uuid4().hex[:20]}"

        validation = self._validate_order(normalized_symbol, budget)
        validation_dict = validation.to_dict()
        if not validation.valid:
            raw = json.dumps({"validation": validation_dict, "reason": validation.blocked_reason}, ensure_ascii=False)
            return OrderResult(
                broker="binance",
                market=OpportunityType.CRYPTO,
                symbol=normalized_symbol,
                side=side,
                budget=budget,
                status="rejected_validation",
                order_id=f"rejected-{cid}",
                client_order_id=cid,
                raw=raw,
                validation=validation_dict,
            )

        payload = {
            "symbol": normalized_symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{validation.normalized_quantity:.12f}".rstrip("0").rstrip("."),
            "newClientOrderId": cid,
        }

        if not self._live_enabled():
            raw = json.dumps({"mode": "stub", "payload": payload, "validation": validation_dict}, ensure_ascii=False)
            return OrderResult(
                broker="binance",
                market=OpportunityType.CRYPTO,
                symbol=normalized_symbol,
                side=side,
                budget=budget,
                status="stub_submitted",
                order_id=f"stub-{cid}",
                client_order_id=cid,
                raw=raw,
                validation=validation_dict,
            )

        data = self._signed_request("POST", "/api/v3/order", payload)
        data["validation"] = validation_dict
        return OrderResult(
            broker="binance",
            market=OpportunityType.CRYPTO,
            symbol=normalized_symbol,
            side=side,
            budget=budget,
            status=data.get("status", "submitted"),
            order_id=str(data.get("orderId", "unknown")),
            client_order_id=cid,
            raw=json.dumps(data, ensure_ascii=False),
            validation=validation_dict,
        )

    def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        normalized = symbol.replace("-", "")
        if not self._live_enabled():
            return {"symbol": normalized, "orderId": order_id, "status": "FILLED", "stub": True}
        return self._signed_request("GET", "/api/v3/order", {"symbol": normalized, "orderId": order_id})

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        normalized = symbol.replace("-", "")
        if not self._live_enabled():
            return {"symbol": normalized, "orderId": order_id, "status": "CANCELED", "stub": True}
        return self._signed_request("DELETE", "/api/v3/order", {"symbol": normalized, "orderId": order_id})


class UnifiedBroker:
    def __init__(self, config: BrokerConfig | None = None) -> None:
        cfg = config or BrokerConfig()
        self.meritz = MeritzBroker(config=cfg)
        self.binance = BinanceBroker(config=cfg)

    def place_order(
        self,
        market: OpportunityType,
        symbol: str,
        budget: float,
        side: str | None = None,
        client_order_id: str | None = None,
    ) -> OrderResult:
        if market == OpportunityType.STOCK:
            return self.meritz.place_order(symbol=symbol, budget=budget, side=side or "buy", client_order_id=client_order_id)
        if market == OpportunityType.CRYPTO:
            return self.binance.place_order(symbol=symbol, budget=budget, side=side or "BUY", client_order_id=client_order_id)
        return OrderResult(
            broker="none",
            market=market,
            symbol=symbol,
            side=side or "none",
            budget=budget,
            status="not_required",
            order_id="none",
            client_order_id=client_order_id or "none",
            raw=f"no_broker_needed market={market.value}",
        )

    def get_order(self, market: OpportunityType, symbol: str, order_id: str) -> dict[str, Any]:
        if market == OpportunityType.STOCK:
            return self.meritz.get_order(order_id)
        if market == OpportunityType.CRYPTO:
            return self.binance.get_order(symbol, order_id)
        return {"orderId": order_id, "status": "N/A"}

    def cancel_order(self, market: OpportunityType, symbol: str, order_id: str) -> dict[str, Any]:
        if market == OpportunityType.STOCK:
            return self.meritz.cancel_order(order_id)
        if market == OpportunityType.CRYPTO:
            return self.binance.cancel_order(symbol, order_id)
        return {"orderId": order_id, "status": "N/A"}
