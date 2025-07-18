#!/bin/bash

# Go to project directory and call this script to activate project specific venv
# FIXME: Instead of pwd, parameterize the project directory and ensure that pyproject.toml exists in that directory

quoteSubst() {
  IFS= read -d '' -r < <(sed -e ':a' -e '$!{N;ba' -e '}' -e 's/[&/\]/\\&/g; s/\n/\\&/g' <<<"$1")
  printf %s "${REPLY%$'\n'}"
}

rm -rf $(pwd)/.venv

python -m venv $(pwd)/.venv

if [[ "$(uname -s)" == *"MINGW"* || "$(uname -s)" == *"CYGWIN"* || "$(uname -s)" == *"MSYS"* ]]; then
    BIN_DIR=$(pwd)/.venv/Scripts
    INTERPRETER=$(pwd -W)/.venv/Scripts/python.exe
else
    BIN_DIR=$(pwd)/.venv/bin
    INTERPRETER=$BIN_DIR/python
fi

"$BIN_DIR/activate"

# Install pinned pip first
pip install -r $(git rev-parse --show-toplevel)/pip-requirements.txt

# Update the lock file
poetry lock

# Generate requirements.txt with Poetry
poetry export -f requirements.txt --without-hashes --output requirements.txt

# Install shared development dependencies and project/library-specific dependencies
pip install -r $(git rev-parse --show-toplevel)/dev-requirements.txt -r requirements.txt

# Create VSCode settings to match the active interpreter
sed "s#{{interpreter_path}}#$(quoteSubst "$INTERPRETER")#" $(git rev-parse --show-toplevel)/vscode_settings_template.json > $(git rev-parse --show-toplevel)/.vscode/settings.json 