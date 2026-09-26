#!/bin/sh
# Publish sources (main) and the web build (gh-pages) to andrewnakas/sf64-cleanroom.
#   games/sf64/publish.sh            (run only after taint_report prints 0 failing)
# Never publishes the dirty tree, dev builds (DEV_RETAIL_AUDIO) or retail files.
set -e
R="$(cd "$(dirname "$0")/../.." && pwd)"
W=D:/n64work/sf64
[ -f $W/clean/DEV_RETAIL_AUDIO ] && { echo "refusing: clean tree has retail audio"; exit 1; }
grep -q " 0 failing" $W/taint_final.log || { echo "refusing: taint_final.log does not say 0 failing"; exit 1; }
EX=$W/export
rm -rf $EX && (cd "$R" && sh games/sf64/export_repo.sh $EX)
cd $EX
git init -q -b main
git -c core.autocrlf=false add -A
git -c user.name=andre -c user.email=treesixtyweather@gmail.com commit -qm "Star Fox 64 clean room: generator, spec, tools

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
gh repo view andrewnakas/sf64-cleanroom >/dev/null 2>&1 || gh repo create andrewnakas/sf64-cleanroom --public \
  --description "Star Fox 64 in the browser, built from the sf64 decomp with every ROM asset regenerated (clean room)"
git remote add origin https://github.com/andrewnakas/sf64-cleanroom.git
git push -q -f origin main
# site
S=$W/site_pub
rm -rf $S && cp -r $W/site $S && cd $S
git init -q -b gh-pages
git add -A
git -c user.name=andre -c user.email=treesixtyweather@gmail.com commit -qm "Web build

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git remote add origin https://github.com/andrewnakas/sf64-cleanroom.git
git push -q -f origin gh-pages
gh api -X POST repos/andrewnakas/sf64-cleanroom/pages -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null 2>&1 || true
gh api repos/andrewnakas/sf64-cleanroom/pages --jq '.html_url + " " + .status'
