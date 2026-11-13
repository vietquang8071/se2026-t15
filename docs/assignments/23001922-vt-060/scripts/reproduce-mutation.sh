#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
: "${AUDIO_DATABASE_URL:?Set AUDIO_DATABASE_URL to an isolated test PostgreSQL server}"
temp_base="$(mktemp -d -t vt060-mutation-XXXXXX)"
tree="$temp_base/worktree"
logs="$(mktemp -d -t vt060-mutation-logs-XXXXXX)"
cleanup() {
  git -C "$root" worktree remove --force "$tree" >/dev/null 2>&1 || true
  rmdir "$temp_base" 2>/dev/null || true
}
trap cleanup EXIT
git -C "$root" worktree add --detach "$tree" HEAD >/dev/null
ln -s "$root/node_modules" "$tree/node_modules"
ln -s "$root/apps/audio/node_modules" "$tree/apps/audio/node_modules"
cp -a "$root/apps/audio/src/generated" "$tree/apps/audio/src/generated"
compile() { node "$root/node_modules/typescript/bin/tsc" -p "$tree/apps/audio/tsconfig.json"; }
run_test() {
  (cd "$tree/apps/audio" && node --test --test-name-pattern='job retry cap|failed job with two attempts' test/http/audio-http.test.mjs)
}
compile
run_test > "$logs/original.log" 2>&1
python3 - "$tree/apps/audio/src/audio/audio.service.ts" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
s=p.read_text()
original='if (job.attempts >= 3)'
assert s.count(original)==1
p.write_text(s.replace(original,'if (!(job.attempts >= 3))'))
PY
git -C "$tree" diff > "$logs/mutation.patch"
compile
set +e
run_test > "$logs/mutation.log" 2>&1
status=$?
set -e
if [ "$status" -eq 0 ] || ! grep -q '202 !== 409' "$logs/mutation.log" || ! grep -q '409 !== 202' "$logs/mutation.log"; then
  echo "Mutation not verified; inspect $logs" >&2
  exit 1
fi
git -C "$tree" restore apps/audio/src/audio/audio.service.ts
compile
run_test > "$logs/restored.log" 2>&1
echo "Mutation killed and restored; logs: $logs"
