.PHONY: help run-tag run-notice run-delete dry-tag dry-notice dry-delete build up down logs

help:
	@echo "Usage:"
	@echo "  make run-tag      - タグ付与スクリプトを実行"
	@echo "  make run-notice   - 剪定通知スクリプトを実行"
	@echo "  make run-delete   - 剪定実行スクリプトを実行"
	@echo "  make dry-tag      - タグ付与スクリプトをdry-run"
	@echo "  make dry-notice   - 剪定通知スクリプトをdry-run"
	@echo "  make dry-delete   - 剪定実行スクリプトをdry-run"
	@echo "  make build        - Dockerイメージをビルド"
	@echo "  make up           - コンテナを起動"
	@echo "  make down         - コンテナを停止"
	@echo "  make logs         - ログを表示"

# 本番実行
run-tag:
	uv run scripts/new_page/tagging.py

run-notice:
	uv run scripts/collab_deletion/notice.py

run-delete:
	uv run scripts/collab_deletion/exec.py

# Dry-run
dry-tag:
	uv run scripts/new_page/tagging.py --dry-run

dry-notice:
	uv run scripts/collab_deletion/notice.py --dry-run

dry-delete:
	uv run scripts/collab_deletion/exec.py --dry-run

# Docker
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f
