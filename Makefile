PROJECT_COMPOSE=deploy/docker-compose.yml

.PHONY: dev-up dev-down migrate seed-demo fake-post test lint

dev-up:
	LLM_MODE=mock docker compose -f $(PROJECT_COMPOSE) --profile dev up -d --build

dev-down:
	docker compose -f $(PROJECT_COMPOSE) --profile dev down -v

migrate:
	PYTHONPATH=. python scripts/apply_migrations.py

seed-demo:
	PYTHONPATH=. python scripts/seed_demo.py

fake-post:
	LLM_MODE=mock PYTHONPATH=. python scripts/dev_fake_ingest.py \
		--channel "Demo Channel" \
		--tg_channel_id 1001 \
		--message_id 42 \
		--text "Тестовый пост для демонстрации."

test:
	mkdir -p reports
	PYTHONPATH=. pytest --junitxml=reports/junit.xml

lint:
	ruff check .
	ruff format --check .
	mypy libs/core
