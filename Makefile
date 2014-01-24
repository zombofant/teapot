PYTHON=python3

docs:
	cd docs; $(MAKE) html

view-docs: docs
	firefox ./docs/build/html/index.html

tests:
	@$(PYTHON) -m unittest tests

.PHONY: docs view-docs tests
