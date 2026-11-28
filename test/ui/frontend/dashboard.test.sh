#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
exec node --test dashboard.test.mjs
