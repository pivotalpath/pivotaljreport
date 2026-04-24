# pivotaljreport

Thin Python client + CLI for the PivotalPath jreport service.

## Install

```
# From GitHub (once the repo is public):
pip install git+https://github.com/pivotalpath/pivotaljreport.git

# Local editable install:
pip install -e C:/pp/code/prod/pivotaljreport
```

## Python usage

```python
import pivotaljreport as pj

pj.authenticate(username="alice", password="...")
result = pj.run(folder="./data", out="./reports")
print(result["pdfs"])
```

`run()` zips the `.xlsx` files in `folder`, uploads them to the server,
polls until the batch finishes, and extracts the returned PDFs into
`out`.

## Command-line usage

```
pivotaljreport run ./data --out ./reports --username alice
# prompts for password (hidden)
```

Fully non-interactive via env vars:

```
export PIVOTALJREPORT_USERNAME=alice
export PIVOTALJREPORT_PASSWORD=...
export PIVOTALJREPORT_BASE_URL=https://apps2.pivotalpath.com/jreport
pivotaljreport run ./data --out ./reports
```

## Configuration

- `PIVOTALJREPORT_BASE_URL` — server base URL
  (default: `https://apps2.pivotalpath.com/jreport`)
- `PIVOTALJREPORT_USERNAME` — CLI default for `--username`
- `PIVOTALJREPORT_PASSWORD` — CLI default for `--password` (skips prompt)

## Notes

- Auth is a placeholder — username/password issues a short-lived bearer
  token. Do not commit credentials; prefer env vars or interactive prompt.
- Input files must match the JPM-style xlsx schema the generator
  expects (sheets: `Fund`, `Benchmark1`, `Benchmark2`, `RFR`, plus
  optional `manager_bio`, `overview`, `terms`, `profile`).
