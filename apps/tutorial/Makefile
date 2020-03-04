.PHONY: clean clean-test clean-pyc clean-build help

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
	docker-compose -f tutorial-2.yml run --no-deps --rm node1 find . -name '*.pyc' -exec rm -f {} +
	docker-compose -f tutorial-2.yml run --no-deps --rm node1 find . -name '*.pyo' -exec rm -f {} +
	docker-compose -f tutorial-2.yml run --no-deps --rm node1 find . -name '*~' -exec rm -f {} +
	docker-compose -f tutorial-2.yml run --no-deps --rm node1 find . -name '__pycache__' -exec rm -fr {} +

down: ## stop and remove containers, networks, images, and volumes
	docker-compose -f tutorial-2.yml down

stop:
	docker-compose -f tutorial-2.yml stop

rm:
	docker-compose -f tutorial-2.yml rm --stop --force

run: rm ## run the example
	docker-compose -f tutorial-2.yml up -d
	sh follow-logs-with-tmux.sh

run-without-tmux: rm ## run the example
	docker-compose -f tutorial-2.yml up -d
