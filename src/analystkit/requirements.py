"""API-free, review-first requirements extraction and traceability."""

from pathlib import Path
import re

import pandas as pd

from .results import AnalysisResult, require, table


LABELS = {
    "decision": re.compile(r"^(?:decision|agreed)\s*[:\-]\s*(.+)$", re.I),
    "action": re.compile(r"^(?:action|todo|follow.?up)\s*[:\-]\s*(.+)$", re.I),
    "requirement": re.compile(r"^(?:requirement|need|user story)\s*[:\-]\s*(.+)$", re.I),
    "acceptance_criterion": re.compile(r"^(?:acceptance|acceptance criterion|ac)\s*[:\-]\s*(.+)$", re.I),
    "question": re.compile(r"^(?:question|open question)\s*[:\-]\s*(.+)$", re.I),
}


def meeting_assistant(notes: str | Path) -> AnalysisResult:
    """Extract explicitly labelled items; never invent owners or decisions."""
    if isinstance(notes, Path):
        content = notes.read_text(encoding="utf-8")
    else:
        content = notes
    if not content.strip():
        raise ValueError("Meeting notes are empty")
    items = []
    unmatched = []
    last_requirement = ""
    for line_number, line in enumerate(content.splitlines(), 1):
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line.strip())
        if not cleaned:
            continue
        match = next(((label, regex.match(cleaned)) for label, regex in LABELS.items()
                      if regex.match(cleaned)), None)
        if match:
            kind, found = match
            body = found.group(1).strip()
            owner_match = re.search(r"\bowner\s*[:=]\s*([^;,]+)", body, flags=re.I)
            owner = owner_match.group(1).strip() if owner_match else ""
            draft_id = f"D-{len(items)+1:03d}"
            linked = last_requirement if kind == "acceptance_criterion" else ""
            if kind == "requirement":
                last_requirement = draft_id
            items.append({"draft_id": draft_id, "type": kind, "text": body,
                          "owner_to_confirm": owner, "source_line": line_number,
                          "linked_requirement": linked, "status": "draft_for_review"})
        else:
            unmatched.append({"source_line": line_number, "text": cleaned})
    return AnalysisResult("requirements_meeting_assistant",
                          f"Extracted {len(items)} explicitly labelled draft items; {len(unmatched)} lines need manual review.",
                          {"Draft items": pd.DataFrame(items, columns=["draft_id", "type", "text", "owner_to_confirm", "source_line", "linked_requirement", "status"]),
                           "Unclassified lines": pd.DataFrame(unmatched, columns=["source_line", "text"])},
                          ["Unlabelled notes are not classified automatically. Review every draft before treating it as agreed.",
                           "Only explicitly labelled acceptance criteria are extracted; all drafts need stakeholder review."],
                          {"rules": "Lines starting Decision, Action, Requirement, Acceptance, or Question are classified; all other lines remain unclassified."})


def traceability(data, *, requirement_id: str, status: str,
                 design: str | None = None, test: str | None = None,
                 acceptance: str | None = None) -> AnalysisResult:
    """Check coverage links; statuses are reported as supplied, not inferred."""
    frame = table(data)
    require(frame, requirement_id, status)
    optional = {"design": design, "test": test, "acceptance": acceptance}
    for name in optional.values():
        if name:
            require(frame, name)
    if frame[requirement_id].isna().any() or frame[requirement_id].astype(str).str.strip().eq("").any():
        raise ValueError("Every requirement needs an ID")
    if frame[requirement_id].duplicated().any():
        raise ValueError("Requirement IDs must be unique")
    checks = frame[[requirement_id, status, "_source_row"] + [name for name in optional.values() if name]].copy()
    checks["review_flags"] = ""
    for label, column in optional.items():
        if column:
            missing = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
            checks.loc[missing, "review_flags"] += f"Missing {label}; "
    open_status = frame[status].isna() | frame[status].astype(str).str.lower().isin(
        ["draft", "open", "blocked", "in progress", "pending", "unresolved"])
    checks.loc[open_status, "review_flags"] += "Open status; "
    counts = frame[status].fillna("(blank)").value_counts().rename_axis("status").reset_index(name="requirements")
    return AnalysisResult("requirements_traceability",
                          f"{len(frame)} requirements tracked; {int(checks['review_flags'].ne('').sum())} need review.",
                          {"Status counts": counts, "Requirement coverage": checks},
                          ["A filled link is not proof that design, testing, or acceptance is complete."],
                          {"requirement_id": requirement_id, "status": status, **optional})
