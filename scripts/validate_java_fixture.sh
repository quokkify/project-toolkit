#!/usr/bin/env bash
# Compile, test, package, and Maven-test the executable Java fixture in isolation.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/project-toolkit-java-fixture-XXXXXX")"
trap 'rm -rf -- "$temporary_root"' EXIT
fixture="$temporary_root/java"
cp -R -- "$root/tests/fixtures/java" "$fixture"
cd -- "$fixture"

mkdir -p build/classes build/test-classes
javac -Xlint:all -d build/classes src/toolkit/App.java
javac -Xlint:all -cp build/classes -d build/test-classes test/toolkit/AppTest.java
java -cp build/classes:build/test-classes toolkit.AppTest
jar --create --file build/toolkit-java-fixture.jar -C build/classes .
mvn --batch-mode --no-transfer-progress test

echo "java fixture: OK"
