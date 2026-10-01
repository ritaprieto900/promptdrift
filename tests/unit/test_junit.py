"""Tests for the JUnit XML writer."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from promptdrift.services.junit import junit_xml
from tests.conftest import make_case_result, make_run


def test_junit_is_valid_xml_with_failures() -> None:
    run = make_run(
        [
            make_case_result("refund", {"contains-a": (1, 3), "contains-b": (3, 3)}),
        ]
    )
    root = ET.fromstring(junit_xml(run))
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("tests") == "2"
    assert suite.get("failures") == "1"

    testcases = suite.findall("testcase")
    assert {case.get("name") for case in testcases} == {"contains-a", "contains-b"}
    failing = [case for case in testcases if case.find("failure") is not None]
    assert len(failing) == 1
    assert failing[0].get("classname") == "refund"
    failure = failing[0].find("failure")
    assert failure is not None
    assert "1/3 samples passed" in (failure.get("message") or "")


def test_junit_all_passing_has_no_failure_elements() -> None:
    run = make_run([make_case_result("c", {"contains-ok": (2, 2)})])
    root = ET.fromstring(junit_xml(run))
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("failures") == "0"
    assert root.find(".//failure") is None


def test_junit_escapes_special_characters() -> None:
    run = make_run([make_case_result("c<1>", {"contains-a&b": (0, 1)})])
    raw = junit_xml(run)
    ET.fromstring(raw)  # must not raise
    assert "<![CDATA[" not in raw
