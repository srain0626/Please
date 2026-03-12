from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
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
    """메리츠증권 API 어댑터.

    NOTE: 메리츠 OpenAPI 서명/헤더 스펙은 계좌권한/상품군 별로 상이할 수 있어
    아래 구현은 운영 전 최신 공식 문서 기준으로 최종 검증이 필요합니다.
    """

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
    def __init__(self, config: BrokerConfig | None = None) -> None:
        self.config = config or BrokerConfig()
        self.api_key = os.getenv("BINANCE_API_KEY", "")
        self.api_secret = os.getenv("BINANCE_API_SECRET", "")

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

    def place_order(self, symbol: str, budget: float, side: str = "BUY", client_order_id: str | None = None) -> OrderResult:
        normalized = symbol.replace("-", "")
        cid = client_order_id or f"binance-{uuid.uuid4().hex[:20]}"
        if not self._live_enabled():
            return OrderResult(
                broker="binance",
                market=OpportunityType.CRYPTO,
                symbol=normalized,
                side=side,
                budget=budget,
                status="stub_submitted",
                order_id=f"stub-{cid}",
                client_order_id=cid,
                raw=f"binance_stub order side={side} symbol={normalized} budget={budget:.2f}",
            )

        data = self._signed_request(
            "POST",
            "/api/v3/order",
            {
                "symbol": normalized,
                "side": side,
                "type": "MARKET",
                "quoteOrderQty": f"{budget:.2f}",
                "newClientOrderId": cid,
            },
        )
        return OrderResult(
            broker="binance",
            market=OpportunityType.CRYPTO,
            symbol=normalized,
            side=side,
            budget=budget,
            status=data.get("status", "submitted"),
            order_id=str(data.get("orderId", "unknown")),
            client_order_id=cid,
            raw=json.dumps(data, ensure_ascii=False),
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
