"""Conservative field suggestions; uncertain mappings require analyst confirmation."""

from dataclasses import dataclass
import re

import pandas as pd


ALIASES = {
    "date": ("date", "dt", "timestamp", "invoice date", "invoice dt", "order date", "bill date"),
    "amount": ("amount", "value", "revenue", "sales", "net value", "net amount", "total"),
    "customer_id": ("customer id", "client id", "client code", "customer code", "buyer id"),
    "transaction_id": ("invoice id", "invoice no", "order id", "transaction id", "bill no"),
    "category": ("product", "category", "segment", "region", "channel"),
}


@dataclass(frozen=True)
class FieldSuggestion:
    field: str
    column: str | None
    confidence: float
    alternatives: tuple[str, ...]
    needs_confirmation: bool


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).casefold()).strip()


def suggest_fields(frame: pd.DataFrame) -> list[FieldSuggestion]:
    """Suggest business fields by names and samples; never silently settle ties."""
    columns = [str(c) for c in frame.columns if c != "_source_row"]
    result = []
    for field, aliases in ALIASES.items():
        scores = []
        for column in columns:
            name = _normal(column)
            exact = any(name == _normal(alias) for alias in aliases)
            contained = any(_normal(alias) in name for alias in aliases if len(_normal(alias)) > 3)
            score = .9 if exact else .65 if contained else 0.
            if score and field == "date":
                sample = frame[column].dropna().head(15)
                if len(sample) and pd.to_datetime(sample, errors="coerce").notna().mean() < .6:
                    score = .3
            if score:
                scores.append((score, column))
        scores.sort(key=lambda pair: (-pair[0], pair[1]))
        best = scores[0] if scores else (0., None)
        alternatives = tuple(col for _, col in scores[1:])
        ambiguous = len(scores) > 1 and scores[0][0] - scores[1][0] < .2
        result.append(FieldSuggestion(field, best[1], best[0], alternatives, best[0] < .8 or ambiguous))
    return result
