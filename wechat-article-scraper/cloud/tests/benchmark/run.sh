#!/usr/bin/env bash
#
# WeChat Scraper Benchmark Runner
# Round 93: Core Functionality Validation
#

set -e

echo "========================================"
echo "WeChat Scraper Benchmark Suite"
echo "Round 93: Core Functionality Validation"
echo "========================================"
echo ""

cd "$(dirname "$0")/../.."

echo "1. Running Scrape Success Rate Benchmark"
echo "----------------------------------------"
npx vitest run tests/benchmark/scrape-benchmark.ts --reporter=verbose

echo ""
echo "2. Running Annotation Accuracy Test"
echo "------------------------------------"
npx vitest run tests/benchmark/annotation-accuracy.ts --reporter=verbose

echo ""
echo "========================================"
echo "Benchmark Complete"
echo "========================================"
