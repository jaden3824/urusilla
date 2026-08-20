"""Named fail-closed errors used across the harness."""


class EvaluationError(RuntimeError):
    """Base class for deterministic evaluation failures."""


class IntegrityError(EvaluationError):
    """A frozen digest, checksum, hash chain, or canonical identity failed."""


class ManifestError(EvaluationError):
    """A run or episode manifest is incomplete, ambiguous, or invalid."""


class ParseFailure(EvaluationError):
    """A representation could not be parsed without guessing."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class LedgerError(EvaluationError):
    """Token, cost, byte, or timing accounting did not reconcile."""


class StatisticsError(EvaluationError):
    """A paired statistical result cannot safely be produced."""


class BudgetStop(EvaluationError):
    """The next call would cross an approved call or dollar ceiling."""


class ApprovalRequired(EvaluationError):
    """The requested execution would require authority not present here."""

