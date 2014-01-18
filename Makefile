docs:
	cd docs; $(MAKE) html

view-docs: docs
	firefox ./docs/build/html/index.html

.PHONY: docs view-docs
