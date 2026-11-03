PY = .venv/bin/python

.PHONY: data test lint ui ui-test perf perf-report staging production live-feed clean promote retrain-feedback playground
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

# ---- running the app (see README.md, "Operator vs. admin") -------------------------------------
staging:             ## admin UI at :8000 -- train/test models here
	$(PY) main.py --port 8000 --app-mode full
production:          ## operator UI at :8001/ -- isolated Kafka+DB, never trains/tests
	LOGSENTINEL_KAFKA_PORT=9192 \
	LOGSENTINEL_TOOLS=$(HOME)/.local/share/logsentinel-prod \
	LOGSENTINEL_DB=data/prod.db \
	$(PY) main.py --port 8001 --app-mode operator
live-feed:           ## standalone external log generator -- simulates a real system producing logs
	$(PY) -m logsentinel.stream.live_feed
playground:          ## PERSONAL TEST ONLY: traffic + random anomaly bursts, to exercise detect/triage/retrain
	$(PY) -m logsentinel.stream.playground
promote:             ## promote a trained bundle to production's own DB: make promote BUNDLE=models/<name>
	$(PY) -m logsentinel.promote $(BUNDLE)
retrain-feedback:    ## retrain folding in confirmed false positives; registers to staging, never activates/promotes
	$(PY) -m logsentinel.models.retrain_feedback
clean:               ## report old runs/models/data (see python -m logsentinel.cleanup --help for --yes)
	$(PY) -m logsentinel.cleanup
