#!/usr/bin/env bash
#
# 依序執行 lint、typecheck、test 與 build。PR 送出前的檢查。
#
# 刻意不含 audit：那個要連網，而這支要能離線跑（理由見 audit.sh 與 .github/workflows/ci.yml）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/lint.sh"
"$SCRIPT_DIR/typecheck.sh"
"$SCRIPT_DIR/test.sh"
"$SCRIPT_DIR/build.sh"
