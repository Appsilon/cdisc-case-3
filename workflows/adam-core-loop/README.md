# adam-core-loop

Mini-master: derive ADaM with `adam-derivation`, validate it against ADaMIG with
`cdisc-core-validation`, and loop until the standards reviewer accepts. A
finding marked `fix` sends the delivery back to derivation in fix mode, where
the agent changes only the program lines the CORE report traces it to.

```
route ─derive─► derive-adam (child: adam-derivation) ─► route ─validate─► validate-adam (child: cdisc-core-validation, adamig) ─accepted─► finish ─► done
  │                  ├─ child not completed ─► child-failed                        ├─ rejected ─► route (next round, ≤ 3 derivations)
  │                  └─ outcome failed ─────► derivation-failed                     └─ child not completed ─► child-failed
  └─ round > 3 ─► exhausted
```

| Step | Executor | What it does |
|---|---|---|
| `route` | script | Reads its own previous output to know which child just returned, picks the next target, and hands on that child's study package as `package`. |
| `derive-adam` | `run-workflow` | `adam-derivation` (pinned version), payload `{package}`, returns its `return-result` output. |
| `validate-adam` | `run-workflow` | `cdisc-core-validation` (pinned version), `standard=adamig`, `onReject=return`, returns its `decide` output. The reviewer task lives in the child run. |
| `finish` | script | `outcome: accepted`, rounds, the CORE files, and the package with a history entry. |

Inputs (both defaulted, see the platform rule on `stepParams`):

- `package` — study package. `start=derive`: kinds `sdtm` + `adam-spec` (+ `sdtm-define`).
  `start=validate`: also `adam`, `adam-program`, `lineage` (+ `adam-define`), e.g. a sponsor's existing delivery.
- `start` — `derive` (default) or `validate`.

Child versions are pinned in `workflow.json` (`definitionVersion`); bump them
when a child is re-registered.

## Test

```bash
python3 tests/test_route.py
```

`tests/seed_defect.py` builds a seeded-defect delivery (one known derivation
bug, run through the real adam-derivation scripts) for an acceptance run with
`start=validate`.
