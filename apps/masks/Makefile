.PHONY: clean clean-test clean-pyc clean-build docs help

.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef

export PRINT_HELP_PYSCRIPT



help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: clean-pyc

clean-pyc: ## remove Python file artifacts
	docker-compose run --no-deps --rm mpcnet find . -name '*.pyc' -exec rm -f {} +
	docker-compose run --no-deps --rm mpcnet find . -name '*.pyo' -exec rm -f {} +
	docker-compose run --no-deps --rm mpcnet find . -name '*~' -exec rm -f {} +
	docker-compose run --no-deps --rm mpcnet find . -name '__pycache__' -exec rm -fr {} +

down: ## stop and remove containers, networks, images, and volumes
	docker-compose down

run: down ## run the example
	docker-compose up -d blockchain
	docker-compose up setup
	docker-compose up -d client
	sh follow-logs-with-tmux.sh

run-without-tmux: down ## run the example
	docker-compose up -d blockchain
	docker-compose up setup
	docker-compose up -d client
	docker-compose logs --follow blockchain mpcnet client

setup: down
	docker-compose up -d blockchain
	docker-compose up setup
	docker-compose down blockchain
