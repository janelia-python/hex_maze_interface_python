# This file is generated automatically from metadata
# File edits may be overwritten!

.PHONY: upload
upload: metadata package twine add clean

MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
MAKEFILE_DIR := $(notdir $(patsubst %/,%,$(dir $(MAKEFILE_PATH))))
GUIX-TIME-MACHINE = guix time-machine -C $(MAKEFILE_DIR)/guix/channels.scm
GUIX-SHELL = $(GUIX-TIME-MACHINE) -- shell -f $(MAKEFILE_DIR)/guix/guix.scm
GUIX-DEV-SHELL = $(GUIX-TIME-MACHINE) -- shell -D -f $(MAKEFILE_DIR)/guix/guix.scm
CONTAINER = --container --emulate-fhs --network --preserve='^DISPLAY$$' --preserve='^TERM$$'
GUIX-CONTAINER = $(GUIX-SHELL) $(CONTAINER)
GUIX-DEV-CONTAINER = $(GUIX-DEV-SHELL) $(CONTAINER)
VENV-SHELL = rm -rf .venv; mkdir .venv; python3 -m venv .venv; source .venv/bin/activate
DOCKER-DEV-IMAGE = docker build -f $(MAKEFILE_DIR)/docker/Dockerfile.dev -t hex_maze_interface-dev .
DOCKER-DEV-CONTAINER = $(DOCKER-DEV-IMAGE); docker run -it hex_maze_interface-dev
DOCKER-IMAGE = $(DOCKER-DEV-IMAGE); docker build -f $(MAKEFILE_DIR)/docker/Dockerfile -t hex_maze_interface .
DOCKER-CONTAINER = $(DOCKER-IMAGE); docker run -it hex_maze_interface

.PHONY: guix-dev-container
guix-dev-container:
	$(GUIX-DEV-CONTAINER)

.PHONY: guix-dev-container-ipython
guix-dev-container-ipython:
	$(GUIX-DEV-CONTAINER) -- ipython --no-autoindent

.PHONY: guix-container
guix-container:
	$(GUIX-CONTAINER) python-ipython --rebuild-cache

.PHONY: requirements.txt
requirements.txt:
	$(GUIX-DEV-CONTAINER) -- $(VENV-SHELL);\
	pip install .;\
	pip freeze --local --exclude hex_maze_interface > requirements.txt;\
	deactivate;\
	rm -rf .venv

.PHONY: docker-dev-container
docker-dev-container:
	$(DOCKER-DEV-CONTAINER)

.PHONY: docker-dev-container-ipython
docker-dev-container-ipython:
	$(DOCKER-DEV-CONTAINER) ipython --no-autoindent

.PHONY: docker-container
docker-container:
	$(DOCKER-CONTAINER)

.PHONY: metadata-edits
metadata-edits:
	$(GUIX-DEV-CONTAINER) -- sh -c "emacs -q --no-site-file --no-site-lisp --no-splash -l $(MAKEFILE_DIR)/emacs/init.el --file $(MAKEFILE_DIR)/metadata.org"

.PHONY: metadata
metadata: requirements.txt
	$(GUIX-DEV-CONTAINER) -- sh -c "emacs --batch -Q  -l $(MAKEFILE_DIR)/emacs/init.el --eval '(process-org \"$(MAKEFILE_DIR)/metadata.org\")'"

.PHONY: package
package:
	$(GUIX-DEV-CONTAINER) -- sh -c "python3 setup.py sdist bdist_wheel"

.PHONY: twine
twine:
	$(GUIX-DEV-CONTAINER) --network --expose=$$HOME/.pypirc --expose=/etc/ssl/certs/ca-certificates.crt -- sh -c "twine upload dist/*"

.PHONY: add
add:
	$(GUIX-DEV-CONTAINER) -- sh -c "git add --all"

.PHONY: clean
clean:
	$(GUIX-DEV-CONTAINER) -- sh -c "git clean -xdf"

PORT-DIR = /dev
PORT = /dev/ttyACM0
GUIX-DEV-CONTAINER-PORT = $(GUIX-DEV-SHELL) $(CONTAINER) --expose=$(PORT-DIR)
GUIX-CONTAINER-PORT = $(GUIX-SHELL) $(CONTAINER) --expose=$(PORT-DIR)
DOCKER-DEV-CONTAINER-PORT = $(DOCKER-DEV-IMAGE); docker run -it --device=$(PORT) hex_maze_interface-dev
DOCKER-CONTAINER-PORT = $(DOCKER-IMAGE); docker run -it --device=$(PORT) hex_maze_interface

.PHONY: guix-dev-container-port-serial
guix-dev-container-port-serial:
	$(GUIX-DEV-CONTAINER-PORT) picocom -- picocom -b 2000000 -f n -y n -d 8 -p 1 -c $(PORT)

.PHONY: guix-dev-container-port-ipython
guix-dev-container-port-ipython:
	$(GUIX-DEV-CONTAINER-PORT) -- ipython --no-autoindent

.PHONY: guix-container-port
guix-container-port:
	$(GUIX-CONTAINER-PORT) python-ipython --rebuild-cache

.PHONY: docker-dev-container-port-ipython
docker-dev-container-port-ipython:
	$(DOCKER-DEV-CONTAINER-PORT) ipython --no-autoindent

.PHONY: docker-container-port
docker-container-port:
	$(DOCKER-CONTAINER-PORT)
