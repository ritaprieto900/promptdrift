"""Minimal JUnit XML writer so CI UIs can display assertion failures natively.

One ``<testcase>`` per case × assertion; a case where 2/3 samples passed an
assertion counts as a failure with the first failure's detail as its body.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from promptdrift.domain.results import Run


def _short(text: str, limit: int = 200) -> str:
    first_line = text.splitlines()[0] if text else ""
    return first_line[:limit]


def junit_xml(run: Run) -> str:
    case_lines: list[str] = []
    tests = 0
    failures = 0
    for case in run.cases:
        for assertion_id, (passed, total) in sorted(case.rates().items()):
            tests += 1
            first_failure = next(
                (
                    outcome.detail
                    for sample in case.samples
                    for outcome in sample.outcomes
                    if outcome.assertion_id == assertion_id and not outcome.passed
                ),
                None,
            )
            if passed == total:
                case_lines.append(
                    f"    <testcase name={quoteattr(assertion_id)} "
                    f"classname={quoteattr(case.case_id)} />"
                )
                continue
            failures += 1
            message = first_failure or f"{passed}/{total} samples passed"
            case_lines.append(
                f"    <testcase name={quoteattr(assertion_id)} "
                f"classname={quoteattr(case.case_id)}>\n"
                f"      <failure message={quoteattr(_short(message))}>"
                f"{escape(message)}</failure>\n"
                f"    </testcase>"
            )
    suite_attrs = (
        f'name={quoteattr(f"promptdrift:{run.suite}")} tests="{tests}" failures="{failures}"'
    )
    body = "\n".join(case_lines)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<testsuites>\n"
        f"  <testsuite {suite_attrs}>\n{body}\n  </testsuite>\n"
        "</testsuites>\n"
    )
