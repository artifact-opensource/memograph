#!/usr/bin/env bash
# Setup script for memograph package
set -e

echo "=== Memograph v0.2.0 Setup ==="
mkdir -p memograph/core memograph/lifecycle memograph/engines memograph/auth docs tests

echo "Creating package structure..."
python -c "import memograph; print('Package import OK, version:', memograph.__version__)" || {
  echo "Install first: pip install -e ."
  exit 1
}

echo "Creating storage dir..."
mkdir -p .memograph_storage

echo "Done. Run: ./venv/bin/pytest tests/"
