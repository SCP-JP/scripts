.PHONY: help run-tag run-notice run-delete dry-tag dry-notice dry-delete

help:
	@echo "Usage:"
	@echo "  make run-tag      - タグ付与スクリプトを実行"
	@echo "  make run-notice   - 剪定通知スクリプトを実行"
	@echo "  make run-delete   - 剪定実行スクリプトを実行"
	@echo "  make dry-tag      - タグ付与スクリプトをdry-run"
	@echo "  make dry-notice   - 剪定通知スクリプトをdry-run"
	@echo "  make dry-delete   - 剪定実行スクリプトをdry-run"

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
