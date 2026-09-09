.PHONY: test bundle-check
test: bundle-check
	python3 -B -m unittest discover -s tests -v
bundle-check:
	python3 -B operations/bundle.py --check
