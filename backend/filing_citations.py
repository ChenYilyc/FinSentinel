"""Check model-supplied quote lines against documents retrieved during this run."""


def check_filing_quotes(content, trace):
    documents = {
        (doc["ticker"], doc["quarter"], doc["published"], doc["url"]): doc
        for step in trace if step["tool"] == "search_filings"
        for doc in step["result"].get("documents", [])
    }
    draft, matched, issues = [], [], []
    for line in content.splitlines():
        fields = [part.strip() for part in line.strip().split("|", 5)]
        if fields[0] != "FILING":
            draft.append(line)
            continue
        if len(fields) != 6:
            issues.append("invalid_format")
            continue
        doc = documents.get(tuple(fields[1:5]))
        if doc is None:
            issues.append("source_not_retrieved")
        elif fields[5] != doc["excerpt"]:
            issues.append("quote_mismatch")
        elif doc not in matched:
            matched.append(doc)
    if documents and not matched and not issues:
        issues.append("missing_quote")
    return "\n".join(draft).strip(), {"matched": matched, "issues": issues}
