PY = .venv/bin/python

.PHONY: data test lint ui ui-test perf perf-report
data:            ## download + build session splits (HDFS_v1, BGL)
	$(PY) -m logsentinel.data.download
	$(PY) -m logsentinel.data.build
test:
	$(PY) -m pytest -q
lint:
	.venv/bin/ruff check src tests
ui:
	cd ui && npm install && npm run build
ui-test:
	cd ui && npm test && npm run typecheck
perf:               ## run E4/E5/E7 (about 2 h; resumable) then build the report
	$(PY) -m logsentinel.experiments.perf run
	$(PY) -m logsentinel.experiments.perf_report
perf-report:        ## regenerate tables and figures from stored runs
	$(PY) -m logsentinel.experiments.perf_report
