PYTHON ?= python3.12
BIN := .venv/bin

.PHONY: install run test lint evaluate docker-build docker-run
install:
	$(PYTHON) -m venv .venv
	$(BIN)/python -m pip install -r requirements-dev.txt
run:
	$(BIN)/uvicorn src.main:app --reload
test:
	$(BIN)/pytest -q
lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
evaluate:
	$(BIN)/python scripts/test_api.py --base-url http://localhost:8000
docker-build:
	docker build -t bookbridge-api .
docker-run:
	docker run --rm -p 8000:8000 bookbridge-api
