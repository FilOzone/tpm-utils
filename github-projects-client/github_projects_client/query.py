"""OR-condition query expansion for GitHub Projects v2 filter syntax."""

from __future__ import annotations


def expand_or_query(query: str) -> list[str]:
    """Expand a query with OR syntax into multiple individual queries.

    Terms before the first parenthesized group form a shared prefix that is
    prepended to every OR branch.  Each ``(...)`` group becomes a separate
    query string.  Groups are separated by the ``OR`` keyword (uppercase).

    Returns a single-element list when no OR syntax is present (passthrough).

    Raises ``ValueError`` for malformed expressions (unmatched parens, nested
    parens, trailing terms, empty groups, ``OR`` without parens, ``OR`` inside
    parens).
    """
    groups: list[str] = []
    prefix_parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    paren_depth = 0
    found_parens = False
    found_or = False
    expect_group = False  # True after OR — next token must be '('
    expect_or = False  # True after ')' — next token must be OR or end
    i = 0
    n = len(query)

    while i < n:
        ch = query[i]

        # Toggle quote state
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
            i += 1
            continue

        if in_quotes:
            current.append(ch)
            i += 1
            continue

        # Open paren
        if ch == "(":
            if paren_depth == 1:
                raise ValueError("Nested parentheses are not supported")
            if expect_or:
                raise ValueError(
                    "Expected OR between groups; consecutive groups require OR"
                )
            paren_depth = 1
            found_parens = True
            expect_group = False
            # Everything collected before first group (and not after a group) is prefix
            if not groups and not found_or:
                token = "".join(current).strip()
                if token:
                    prefix_parts.append(token)
                current = []
            elif current:
                # Text between ')' and '(' that isn't OR
                token = "".join(current).strip()
                if token:
                    raise ValueError(
                        "Filter terms after the last group are not allowed"
                    )
                current = []
            i += 1
            continue

        # Close paren
        if ch == ")":
            if paren_depth == 0:
                raise ValueError("Unexpected closing parenthesis")
            paren_depth = 0
            group_content = "".join(current).strip()
            if not group_content:
                raise ValueError("Empty group")
            groups.append(group_content)
            current = []
            expect_or = True
            i += 1
            continue

        # Check for OR keyword (outside quotes, outside parens)
        if paren_depth == 0 and ch in ("O", "o") and query[i : i + 2] == "OR":
            # Ensure OR is whitespace-bounded
            before_ok = (i == 0) or query[i - 1] in (" ", "\t")
            after_ok = (i + 2 >= n) or query[i + 2] in (" ", "\t")
            if before_ok and after_ok:
                found_or = True
                expect_or = False
                expect_group = True
                token = "".join(current).strip()
                if token:
                    # Text before OR that's not in a group — means OR without parens
                    if not found_parens:
                        raise ValueError("OR requires parenthesized groups")
                    raise ValueError(
                        "Filter terms after the last group are not allowed"
                    )
                current = []
                i += 2
                continue

        # Check for OR inside parens
        if paren_depth == 1 and ch in ("O", "o") and query[i : i + 2] == "OR":
            before_ok = (i == 0) or query[i - 1] in (" ", "\t")
            after_ok = (i + 2 >= n) or query[i + 2] in (" ", "\t")
            if before_ok and after_ok:
                raise ValueError("OR inside parentheses is not supported")

        current.append(ch)
        i += 1

    # Post-loop checks
    if in_quotes:
        raise ValueError("Unmatched quote")

    if paren_depth != 0:
        raise ValueError("Unmatched opening parenthesis")

    if expect_group:
        raise ValueError("OR must be followed by a parenthesized group")

    # No parens and no OR found — passthrough
    if not found_parens and not found_or:
        return [query]

    # OR found but no parens
    if found_or and not found_parens:
        raise ValueError("OR requires parenthesized groups")

    # Trailing terms after last group
    trailing = "".join(current).strip()
    if trailing:
        raise ValueError("Filter terms after the last group are not allowed")

    prefix = " ".join(prefix_parts).strip()

    if not groups:
        return [query]

    # Single group, no OR — strip parens and combine with prefix
    if len(groups) == 1 and not found_or:
        combined = f"{prefix} {groups[0]}".strip()
        return [combined]

    return [f"{prefix} {g}".strip() for g in groups]
