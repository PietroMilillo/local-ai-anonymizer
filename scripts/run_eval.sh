#!/bin/zsh
# Full comparison. Runs models one at a time and unloads each before the next.
set -e
cd "$(dirname "$0")/.."
python3 -m eval.evaluate --config regex
python3 -m eval.evaluate --config llm:gpt-oss:20b --no-verify
python3 -m eval.evaluate --config llm:gpt-oss:20b
ollama stop gpt-oss:20b || true
python3 -m eval.evaluate --config llm:gpt-oss:120b
ollama stop gpt-oss:120b || true
