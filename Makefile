PYTHON ?= python3
.PHONY: setup doctor test build chat worker
setup:
	$(PYTHON) -m dafeiyu setup
doctor:
	$(PYTHON) -m dafeiyu doctor
test:
	$(PYTHON) -m unittest discover -s tests -v
build:
	$(PYTHON) -m compileall -q dafeiyu
chat:
	$(PYTHON) -m dafeiyu
worker:
	$(PYTHON) -m dafeiyu worker
