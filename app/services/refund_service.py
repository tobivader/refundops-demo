"""Transform a support issue into the application's refund schema."""

from pydantic import ValidationError

from app.models.refund import RefundEvent
from app.models.webhook import GitHubIssue
from app.repositories.refund_repository import RefundRepository, SaveResult


class InvalidRefundError(ValueError):
    """A completed ticket is missing usable refund information."""


class RefundService:
    def __init__(self, repository: RefundRepository | None = None):
        self.repository = repository if repository is not None else RefundRepository()

    def process_refund(self, issue: GitHubIssue, delivery_id: str) -> SaveResult:
        refund = self.extract_refund(issue)
        return self.repository.save(refund, delivery_id)

    # Only these explicit fields are extracted; ticket descriptions are ignored.
    FIELD_NAMES = {
        "customer id": "customer_id",
        "refund amount": "refund_amount",
        "refund reason": "refund_reason",
        "analyst": "analyst",
    }

    def extract_refund(self, issue: GitHubIssue) -> RefundEvent:
        fields = {}
        for line in (issue.body or "").splitlines():
            label, separator, value = line.partition(":")
            field = self.FIELD_NAMES.get(label.strip().lower())
            if not separator or field is None:
                continue
            if field in fields:
                raise InvalidRefundError(f"Duplicate field: {field}")
            fields[field] = value.strip()

        missing = [name for name in self.FIELD_NAMES.values() if name not in fields]
        if missing:
            raise InvalidRefundError("Missing refund fields: " + ", ".join(missing))
        if issue.updated_at is None:
            raise InvalidRefundError("Missing issue updated_at timestamp")

        try:
            return RefundEvent.model_validate({
                **fields,
                "ticket_id": issue.number,
                # Use the source timestamp so redelivery doesn't change the date.
                "refund_date": issue.updated_at,
                "status": "completed",
            })
        except ValidationError as error:
            invalid = sorted({str(item["loc"][0]) for item in error.errors()})
            raise InvalidRefundError("Invalid refund fields: " + ", ".join(invalid)) from None
