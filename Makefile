PYTHON=python3
TESTSARGS=-o tests -p"*.py"

docs:
	cd docs; $(MAKE) html

view-docs: docs
	firefox ./docs/build/html/index.html

tests:
	@$(PYTHON) run_tests.py $(TESTSARGS) -q -f

tests-verbose:
	@$(PYTHON) run_tests.py $(TESTSARGS)

.PHONY: docs view-docs tests tests-verbose
