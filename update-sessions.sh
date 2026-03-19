#!/bin/bash
# Copy any new CSVs from sessions/ to public/sessions/ and update the manifest
cd "$(dirname "$0")"
mkdir -p public/sessions
cp sessions/*.csv public/sessions/ 2>/dev/null
cd public/sessions
ls -1 *.csv 2>/dev/null | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin]))" > ../sessions.json
echo "Updated sessions.json: $(cat ../sessions.json)"
