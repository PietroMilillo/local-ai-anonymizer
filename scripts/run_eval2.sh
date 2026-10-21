#!/bin/zsh
# Rerun after the gazetteer: main corpus, then the held-out-places corpus (seed 11).
set -e
cd "$(dirname "$0")/.."
python3 -m eval.evaluate --config regex --out results/run3
python3 -m eval.evaluate --config llm:gpt-oss:20b --out results/run3
python3 -m eval.evaluate --corpus corpus_heldout --config regex --out results/heldout
python3 -m eval.evaluate --corpus corpus_heldout --config llm:gpt-oss:20b --out results/heldout
ollama stop gpt-oss:20b || true
