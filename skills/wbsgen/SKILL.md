---
name: wbsgen
description: Use when an AI agent needs to create, update, validate, recover, or export a WBS-GEN project with a distributed zipapp.
---

# WBS-GEN

Use this Skill when a user asks to create, update, validate, recover, or export a WBS-GEN project with the distributed `wbsgen.pyz`.

Use the Python command available in the environment. The examples use `python3`;
on Windows this may be `python`.

## Discover the installed CLI

Treat the supplied zipapp as the command contract. Run `wbsgen describe` first, saving its JSON output to a local command-map file. Before choosing a command, print only its top-level command names; do not infer a verb such as `create` from the user request.

```sh
python3 wbsgen.pyz describe > .wbsgen-command-map.json
python3 -c 'import json; print("\n".join(item["name"] for item in json.load(open(".wbsgen-command-map.json"))["commands"]))'
```

Do not print or pretty-print command-map entries. Select an exact command name from that short list, then read only that command's `--help` when its arguments, options, or examples are needed. Use the map only to check whether that selected update supports `--dry-run`.

Do not rely on a copied command list, and do not infer an option from an older WBS-GEN version.

## Classify the request

Classify the user request before changing files:

1. Create a new project from JSON.
2. Update an existing WBS-GEN HTML project.
3. Diagnose and recover from validation errors.
4. Export an existing project to JSON, Markdown, CSV, or XLSX.

If a request spans multiple classes, perform and verify one confirmed change at a time.

## Safe mutation loop

For every command that changes an input file:

1. State the target file and the requested change.
2. Use the selected command's `--dry-run` when `describe` reports that it is available.
3. Review the dry-run result before applying the change.
4. Apply only the confirmed change.
5. Run `validate --json` after the update.
6. Use `show` or `export` to confirm the requested result.

Do not overwrite an existing output or make a destructive change until the user has confirmed the target and intent.

When a CLI dry-run shows only the requested data update and
`_wbsgen.generatedAt`, treat `generatedAt` as an allowed generated timestamp.
It records when WBS-GEN rendered the HTML; it is not user project data. Do not
stop a safe update solely because that field changes. Stop if the dry-run
changes any other unrequested project data.

## Recovery and stop conditions

Use CLI diagnostics and the selected command's help to recover from validation errors. Do not edit generated HTML or embedded JSON directly to bypass a diagnosis.

Stop and ask the user when the intended change is ambiguous, destructive, or cannot be safely recovered through the CLI. If the request conflicts with the CLI contract, explain the conflict instead of silently changing the requested result.
