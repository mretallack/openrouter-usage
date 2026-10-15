VENV = venv
PYTHON = $(VENV)/bin/python3

.PHONY: setup run clean

setup: $(VENV)/bin/activate

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	touch $(VENV)/bin/activate

run: setup
	@$(PYTHON) openrouter_usage.py

clean:
	rm -rf $(VENV)
