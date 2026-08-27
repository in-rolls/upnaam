.PHONY: sync format lint test build ci ci-docker clean

sync:
	uv sync --all-groups

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pydoclint src/upnaam

test:
	uv run pytest --cov=upnaam --cov-report=term-missing --cov-fail-under=90

build:
	uv build

ci: lint test build

ci-docker:
	docker run --rm -e COVERAGE_FILE=/tmp/.coverage -e DEBIAN_FRONTEND=noninteractive -e PIP_ROOT_USER_ACTION=ignore -e RUFF_CACHE_DIR=/tmp/ruff-cache -e UV_CACHE_DIR=/tmp/uv-cache -e UV_PROJECT_ENVIRONMENT=/tmp/upnaam-venv -v "$(PWD):/workspace" -w /workspace python:3.13-slim sh -c "apt-get update && apt-get install -y --no-install-recommends libatomic1 && pip install uv && uv sync --group dev && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pydoclint src/upnaam && uv run pytest -o cache_dir=/tmp/pytest-cache --cov=upnaam --cov-report=term-missing --cov-fail-under=90 && uv build --out-dir /tmp/dist"

clean:
	rm -rf build dist htmlcov .coverage .pytest_cache .ruff_cache
