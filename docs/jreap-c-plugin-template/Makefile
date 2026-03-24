.PHONY: install test typecheck check all

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

typecheck:
	pyright jreap_decoder/

# Run both tests and type checking
check: test typecheck

all: install check
