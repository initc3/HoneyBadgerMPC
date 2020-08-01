.PHONY: clean clean-pyc rm-dbs help

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

clean: clean-pyc rm-dbs rm-preprocessing

rm-dbs:
	docker-compose run --no-deps --rm hbmpc.peer0.io rm -rf apps/asynchromix2/db*

rm-contract-address-file:
	docker-compose run --no-deps --rm hbmpc.peer0.io rm -rf apps/asynchromix2/public-data/contract_address

rm-preprocessing:
	docker-compose run --no-deps --rm hbmpc.peer0.io rm -rf sharedata/*

clean-pyc: ## remove Python file artifacts
	docker-compose run --no-deps --rm hbmpc.peer0.io find . -name '*.pyc' -exec rm -f {} +
	docker-compose run --no-deps --rm hbmpc.peer0.io find . -name '*.pyo' -exec rm -f {} +
	docker-compose run --no-deps --rm hbmpc.peer0.io find . -name '*~' -exec rm -f {} +
	docker-compose run --no-deps --rm hbmpc.peer0.io find . -name '__pycache__' -exec rm -fr {} +

down: ## stop and remove containers, networks, images, and volumes
	docker-compose down

stop:
	docker-compose stop eth.blockchain.io hbmpc.peer0.io hbmpc.peer1.io hbmpc.peer2.io hbmpc.peer3.io

rm:
	docker-compose rm --stop --force eth.blockchain.io hbmpc.peer0.io hbmpc.peer1.io hbmpc.peer2.io hbmpc.peer3.io hbmpc.coordinator.io

run: down rm clean ## run the example
	docker-compose up -d eth.blockchain.io
	docker-compose up hbmpc.coordinator.io
	docker-compose up -d hbmpc.client.io
	sh follow-sim-logs-with-tmux.sh
