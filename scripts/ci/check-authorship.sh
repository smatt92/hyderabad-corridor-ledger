#!/usr/bin/env bash
# Authorship gate: checks every commit reachable from REV (default HEAD).
#
# A commit fails when:
#   - its author or committer is not Sahil Mathew <sahil.matt@gmail.com>
#   - its message contains any line of forbidden-commit-text.txt
#     (case-insensitive substring)
#   - it carries no signature
#   - in CI (GITHUB_REPOSITORY set): GitHub does not report a valid signature
#     made by smatt92's own key
#
# Rules and rationale: CLAUDE.md.
set -euo pipefail

EXPECTED_NAME='Sahil Mathew'
EXPECTED_EMAIL='sahil.matt@gmail.com'
EXPECTED_SIGNER='smatt92'
PATTERNS="$(cd "$(dirname "$0")" && pwd)/forbidden-commit-text.txt"
BATCH_SIZE=50

rev="${1:-HEAD}"
checked=0
failures=0

fail() {
  echo "::error::commit ${1:0:12}: $2"
  failures=$((failures + 1))
}

expect() {  # sha, field, actual, expected
  [ "$3" = "$4" ] || fail "$1" "$2 is '$3', expected '$4'"
}

git rev-parse --verify --quiet "$rev^{commit}" >/dev/null \
  || { echo "::error::$rev is not a commit"; exit 1; }

while IFS= read -r sha; do
  checked=$((checked + 1))

  expect "$sha" 'author name'     "$(git log -1 --format=%an "$sha")" "$EXPECTED_NAME"
  expect "$sha" 'author email'    "$(git log -1 --format=%ae "$sha")" "$EXPECTED_EMAIL"
  expect "$sha" 'committer name'  "$(git log -1 --format=%cn "$sha")" "$EXPECTED_NAME"
  expect "$sha" 'committer email' "$(git log -1 --format=%ce "$sha")" "$EXPECTED_EMAIL"

  if hits=$(git log -1 --format=%B "$sha" | grep -ioF -f "$PATTERNS"); then
    fail "$sha" "message contains forbidden text: $(printf '%s\n' "$hits" | sort -fu | paste -sd, -)"
  fi

  header=$(git cat-file commit "$sha" | sed -n '1,/^$/p')
  grep -q '^gpgsig' <<<"$header" || fail "$sha" 'commit is not signed'
done < <(git rev-list "$rev")

github_verify() {  # checks the shas in the global batch array
  local owner=${GITHUB_REPOSITORY%/*} repo=${GITHUB_REPOSITORY#*/} query i result idx verdict
  query="query { repository(owner: \"$owner\", name: \"$repo\") {"
  for i in "${!batch[@]}"; do
    query+=" c$i: object(oid: \"${batch[$i]}\") { ... on Commit { signature { isValid state wasSignedByGitHub signer { login } } } }"
  done
  query+=' } }'

  result=$(gh api graphql -f query="$query" --jq '
    .data.repository | to_entries[] | "\(.key | ltrimstr("c")) " + (
      if .value == null then "missing"
      elif .value.signature == null then "unsigned"
      elif .value.signature.isValid != true then "invalid:\(.value.signature.state)"
      elif .value.signature.wasSignedByGitHub then "github-signed"
      else "signer:\(.value.signature.signer.login // "unknown")" end)')

  [ "$(grep -c . <<<"$result")" -eq "${#batch[@]}" ] \
    || { echo "::error::GitHub returned an incomplete verification result"; exit 1; }

  while read -r idx verdict; do
    case $verdict in
      "signer:$EXPECTED_SIGNER") ;;
      missing)       fail "${batch[$idx]}" 'not found on GitHub' ;;
      unsigned)      fail "${batch[$idx]}" 'GitHub reports no signature' ;;
      invalid:*)     fail "${batch[$idx]}" "GitHub reports the signature as ${verdict#invalid:}" ;;
      github-signed) fail "${batch[$idx]}" 'signed by GitHub, not by Sahil Mathew' ;;
      *)             fail "${batch[$idx]}" "signed by ${verdict#signer:}, expected $EXPECTED_SIGNER" ;;
    esac
  done <<<"$result"
}

if [ -n "${GITHUB_REPOSITORY:-}" ]; then
  batch=()
  while IFS= read -r sha; do
    batch+=("$sha")
    if [ "${#batch[@]}" -eq "$BATCH_SIZE" ]; then
      github_verify
      batch=()
    fi
  done < <(git rev-list "$rev")
  [ "${#batch[@]}" -eq 0 ] || github_verify
else
  echo "note: signature validity is checked against GitHub only in CI"
fi

if [ "$failures" -gt 0 ]; then
  echo "authorship: $failures problem(s) across $checked commit(s)"
  exit 1
fi
echo "authorship: $checked commit(s) OK"
