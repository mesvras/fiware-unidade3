import pytest

from checks import check
from tests.examples import load_examples, load_invalid, without_context

EXAMPLES = load_examples()
BYID = {e["id"]: without_context(e) for e in EXAMPLES}
INVALID = load_invalid()


@pytest.mark.parametrize("entity", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_examples_pass(entity):
    assert check(without_context(entity), BYID) == []


@pytest.mark.parametrize("name,entity,expected", INVALID, ids=[c[0] for c in INVALID])
def test_invalid_cases_fail_with_expected_reason(name, entity, expected):
    e = without_context(entity)
    related = {k: v for k, v in BYID.items() if k != e["id"]}
    errors = check(e, related)
    assert any(expected in x for x in errors), errors
