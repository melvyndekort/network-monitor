.PHONY: test test-lambdas test-collector

test: test-lambdas test-collector

test-lambdas:
	@for dir in lambdas/*/; do \
		if [ -f "$$dir/test_handler.py" ]; then \
			echo "=== Testing $$dir ===" && \
			cd $$dir && uv run pytest -v && cd ../.. || exit 1; \
		fi; \
	done

test-collector:
	@echo "=== Testing data-collector ==="
	@$(MAKE) -C data-collector test
