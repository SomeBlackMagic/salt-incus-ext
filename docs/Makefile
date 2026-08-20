# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
# Prefer the project's development environment for direct ``make`` calls.
# This prevents an activated test-only nox environment from accidentally
# selecting a sphinx-build that does not contain the ``docs`` extras. CI and
# installations without a project .venv continue to resolve sphinx-build from
# PATH. The value can always be overridden explicitly on the command line.
PROJECT_SPHINXBUILD := ../.venv/bin/sphinx-build
SPHINXBUILD   ?= $(if $(wildcard $(PROJECT_SPHINXBUILD)),$(PROJECT_SPHINXBUILD),sphinx-build)
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
