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

rm-dbs:
	docker-compose run --no-deps --rm mpcnet rm -rf apps/masks/db*

down: ## stop and remove containers, networks, images, and volumes
	docker-compose down

down-sim: ## stop and remove containers, networks, images, and volumes
	docker-compose -f sim.yml down

stop:
	docker-compose stop blockchain mpcnet

rm:
	docker-compose rm --stop --force blockchain setup mpcnet client

run: down rm clean ## run the example
	docker-compose up -d blockchain
	docker-compose up setup
	docker-compose up -d client
	sh follow-logs-with-tmux.sh

run-without-tmux: rm clean ## run the example
	docker-compose up -d blockchain
	docker-compose up setup
	docker-compose up -d client
	docker-compose logs --follow blockchain mpcnet client

setup: rm clean
	docker-compose up -d blockchain
	docker-compose up setup
	docker-compose rm --stop --force blockchain

### sim
clean-sim: clean-sim-pyc

clean-sim-pyc: ## remove Python file artifacts
	docker-compose -f sim.yml run --no-deps --rm hbmpc.peer0.io find . -name '*.pyc' -exec rm -f {} +
	docker-compose -f sim.yml run --no-deps --rm hbmpc.peer0.io find . -name '*.pyo' -exec rm -f {} +
	docker-compose -f sim.yml run --no-deps --rm hbmpc.peer0.io find . -name '*~' -exec rm -f {} +
	docker-compose -f sim.yml run --no-deps --rm hbmpc.peer0.io find . -name '__pycache__' -exec rm -fr {} +

down-sim: ## stop and remove containers, networks, images, and volumes
	docker-compose -f sim.yml down

stop-sim:
	docker-compose -f sim.yml stop eth.blockchain.io hbmpc.peer0.io hbmpc.peer1.io hbmpc.peer2.io hbmpc.peer3.io

rm-sim:
	docker-compose -f sim.yml rm --stop --force eth.blockchain.io hbmpc.peer0.io hbmpc.peer1.io hbmpc.peer2.io hbmpc.peer3.io hbmpc.coordinator.io

run-sim: down-sim rm-sim clean-sim ## run the example
	docker-compose -f sim.yml up -d eth.blockchain.io
	docker-compose -f sim.yml up hbmpc.coordinator.io
	docker-compose -f sim.yml up -d hbmpc.client.io
	sh follow-sim-logs-with-tmux.sh

run-mpcnet:
	docker-compose -f sim.yml up -d eth.blockchain.io
	docker-compose -f sim.yml up hbmpc.coordinator.io
	docker-compose -f sim.yml up -d hbmpc.peer0.io
	docker-compose -f sim.yml up -d hbmpc.peer1.io
	docker-compose -f sim.yml up -d hbmpc.peer2.io
	docker-compose -f sim.yml up -d hbmpc.peer3.io
	sh follow-sim-logs-with-tmux.sh
