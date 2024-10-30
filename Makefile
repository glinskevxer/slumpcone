PY ?= python
SRC = src/slumpcone
TESTS = tests

.PHONY: install lint fmt type test cov check clean

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check $(SRC) $(TESTS)

fmt:
	$(PY) -m ruff format $(SRC) $(TESTS)

type:
	$(PY) -m mypy

test:
	$(PY) -m pytest -q

check: lint type test

wheel:
	$(PY) -m build --wheel

demo:
	rm -f demo.sqlite3
	$(PY) -m slumpcone.cli.main --register demo.sqlite3 demo seed
	$(PY) -m slumpcone.cli.main --register demo.sqlite3 demo tour

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build .coverage coverage.xml
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
