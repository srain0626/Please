from __future__ import annotations

import json
import random
from dataclasses import dataclass

from .persistence import SQLiteStore


@dataclass
class DistributionResult:
    run_id: int
    status: str
    external_ref: str
    notes: str


class DistributionAdapterBase:
    adapter_name = "base"

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def submit(self, *, target_id: int, channel_id: int, mechanism_id: int, execution_mode: str) -> DistributionResult:
        raise NotImplementedError

    def _create_run(
        self,
        *,
        target_id: int,
        channel_id: int,
        mechanism_id: int,
        execution_mode: str,
        status: str,
        external_ref: str,
        notes: str,
    ) -> int:
        return self.store.create_distribution_run(
            target_id=target_id,
            channel_id=channel_id,
            mechanism_id=mechanism_id,
            execution_mode=execution_mode,
            status=status,
            external_ref=external_ref,
            notes=notes,
        )


class BlogChannelAdapterStub(DistributionAdapterBase):
    adapter_name = "blog_stub"

    def submit(self, *, target_id: int, channel_id: int, mechanism_id: int, execution_mode: str) -> DistributionResult:
        ext = f"blog-post-{target_id}-{channel_id}"
        run_id = self._create_run(
            target_id=target_id,
            channel_id=channel_id,
            mechanism_id=mechanism_id,
            execution_mode=execution_mode,
            status="submitted",
            external_ref=ext,
            notes="blog distribution submitted",
        )
        self.store.update_distribution_run_status(run_id, "delivered", notes="blog post published")
        self.store.record_conversion_event(
            run_id=run_id,
            target_id=target_id,
            mechanism_id=mechanism_id,
            event_type="impression",
            value_estimate=0.0,
            metadata_json=json.dumps({"adapter": self.adapter_name}),
        )
        return DistributionResult(run_id=run_id, status="delivered", external_ref=ext, notes="published")


class OutreachChannelAdapterStub(DistributionAdapterBase):
    adapter_name = "outreach_stub"

    def submit(self, *, target_id: int, channel_id: int, mechanism_id: int, execution_mode: str) -> DistributionResult:
        ext = f"outreach-{target_id}-{channel_id}"
        run_id = self._create_run(
            target_id=target_id,
            channel_id=channel_id,
            mechanism_id=mechanism_id,
            execution_mode=execution_mode,
            status="submitted",
            external_ref=ext,
            notes="outreach message submitted",
        )
        responded = (target_id + channel_id + mechanism_id) % 2 == 0
        if responded:
            self.store.update_distribution_run_status(run_id, "responded", notes="client replied")
            self.store.record_conversion_event(
                run_id=run_id,
                target_id=target_id,
                mechanism_id=mechanism_id,
                event_type="reply",
                value_estimate=0.0,
                metadata_json=json.dumps({"adapter": self.adapter_name}),
            )
            self.store.apply_feedback_event("proposal_accepted", mechanism_id)
        else:
            self.store.update_distribution_run_status(run_id, "failed", notes="no response yet")
            self.store.record_conversion_event(
                run_id=run_id,
                target_id=target_id,
                mechanism_id=mechanism_id,
                event_type="no_response",
                value_estimate=0.0,
                metadata_json=json.dumps({"adapter": self.adapter_name}),
            )
            self.store.apply_feedback_event("no_response", mechanism_id)
        return DistributionResult(
            run_id=run_id,
            status="responded" if responded else "failed",
            external_ref=ext,
            notes="outreach simulation",
        )


class MarketplaceChannelAdapterStub(DistributionAdapterBase):
    adapter_name = "marketplace_stub"

    def submit(self, *, target_id: int, channel_id: int, mechanism_id: int, execution_mode: str) -> DistributionResult:
        ext = f"market-{target_id}-{channel_id}"
        run_id = self._create_run(
            target_id=target_id,
            channel_id=channel_id,
            mechanism_id=mechanism_id,
            execution_mode=execution_mode,
            status="submitted",
            external_ref=ext,
            notes="marketplace listing submitted",
        )
        converted = random.Random(target_id + mechanism_id).random() > 0.4
        if converted:
            self.store.update_distribution_run_status(run_id, "converted", notes="sale conversion")
            self.store.record_conversion_event(
                run_id=run_id,
                target_id=target_id,
                mechanism_id=mechanism_id,
                event_type="sale",
                value_estimate=45.0,
                metadata_json=json.dumps({"adapter": self.adapter_name, "currency": "USD"}),
            )
            self.store.apply_feedback_event("sale", mechanism_id)
        else:
            self.store.update_distribution_run_status(run_id, "failed", notes="listing rejected")
            self.store.record_conversion_event(
                run_id=run_id,
                target_id=target_id,
                mechanism_id=mechanism_id,
                event_type="rejected",
                value_estimate=0.0,
                metadata_json=json.dumps({"adapter": self.adapter_name}),
            )
            self.store.apply_feedback_event("rejected", mechanism_id)
        return DistributionResult(
            run_id=run_id,
            status="converted" if converted else "failed",
            external_ref=ext,
            notes="marketplace simulation",
        )


def adapter_for_channel_type(channel_type: str, store: SQLiteStore) -> DistributionAdapterBase:
    normalized = channel_type.strip().lower()
    if normalized == "blog":
        return BlogChannelAdapterStub(store)
    if normalized in {"email", "direct_outreach", "social"}:
        return OutreachChannelAdapterStub(store)
    if normalized in {"marketplace", "landing_page"}:
        return MarketplaceChannelAdapterStub(store)
    return OutreachChannelAdapterStub(store)
