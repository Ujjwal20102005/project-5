.PHONY: install test bench run docker up
install:
	pip install -r requirements.txt
test:
	python -m pytest
bench:
	PYTHONPATH=src python scripts/benchmark.py
run:
	PYTHONPATH=src python -m hpapp.main
docker:
	docker build -f docker/Dockerfile -t hpapp:2.1.0 .
up:
	docker compose -f docker/docker-compose.yml up --build
