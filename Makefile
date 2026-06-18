.PHONY: venv install env setup dev health

venv:
	python3 -m venv .venv

install: venv
	. .venv/bin/activate && pip install -e .

env:
	test -f .env || cp .env.example .env

setup: install env

dev:
	. .venv/bin/activate && uvicorn app.main:app --reload --port 8000

health:
	curl http://localhost:8000/health
