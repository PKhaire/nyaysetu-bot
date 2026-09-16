"""Customer release policy for Draft Studio document products.

The order's release status is the durable commercial boundary.  A beta order
may collect and retain questionnaire answers under the normal draft retention
rules, but it cannot create artifacts, payment links, advocate work or an
issued document.
"""

from __future__ import annotations

from config import DOCUMENT_STUDIO_CUSTOMER_MODE
from models import DocumentOrder


BETA_RELEASE_STATUS = "BETA"


def beta_mode_enabled() -> bool:
    """Return the global, fail-closed customer mode for document products."""

    return DOCUMENT_STUDIO_CUSTOMER_MODE == "beta"


def cheque_notice_beta_enabled(
    *,
    environment: str,
    staging_uat_enabled: bool,
) -> bool:
    """Allow public beta intake, retaining an explicit staging kill switch."""

    if not beta_mode_enabled():
        return False
    return environment == "production" or (
        environment == "staging" and staging_uat_enabled
    )


def stamp_new_order(order: DocumentOrder) -> None:
    """Persist the beta restriction on a newly created customer order."""

    if beta_mode_enabled():
        order.release_status = BETA_RELEASE_STATUS
        order.price_minor = None


def order_is_beta(order: DocumentOrder) -> bool:
    """Return whether this order is permanently restricted to beta intake."""

    return order.release_status == BETA_RELEASE_STATUS


def document_commerce_disabled(order: DocumentOrder) -> bool:
    """Fail closed globally and preserve the restriction on beta orders."""

    return beta_mode_enabled() or order_is_beta(order)
