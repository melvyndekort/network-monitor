.PHONY: clean install update-deps test build full-build pylint run
.DEFAULT_GOAL: build

clean:
	@rm -rf .pytest_cache dist __pycache__ */__pycache__

install: clean
	@uv sync --all-extras

update-deps:
	@uv sync --upgrade --all-extras

test: install
	@uv run pytest

build: test
	@uv build

full-build: clean
	@docker build -t data-collector .

pylint:
	@uv run pylint data_collector

run: install
	@uv run python3 -m data_collector.main
