"""Generate the carried ADaMIG local rules (artifacts/rules/adamig/*.yml).

CORE publishes no ADaMIG rules, so the ADaM checkpoint runs these through
`core validate -lr`. Each rule cites the ADaMIG 1.3 requirement it encodes.
Edit RULES and re-run; tests/test_adam_rules.py proves each one fires.
"""

from __future__ import annotations

from pathlib import Path

import yaml

TARGET = Path(__file__).resolve().parent.parent / "artifacts" / "rules" / "adamig"

RULES = [
    {
        "id": "MF-ADAM-001", "domains": ["ADSL"], "variables": ["USUBJID"],
        "description": "ADSL contains one record per subject.",
        "citation": "ADaMIG 1.3 Section 3.1: ADSL contains one record per subject.",
        "message": "USUBJID occurs on more than one ADSL record.",
        "check": {"all": [{"name": "USUBJID", "operator": "is_not_unique_set", "value": ["STUDYID"]}]},
    },
    {
        "id": "MF-ADAM-002", "domains": ["ADSL"], "variables": ["SAFFL"],
        "description": "The safety population flag SAFFL is populated with Y or N for every subject.",
        "citation": "ADaMIG 1.3 Section 3.2.4: subject-level population flags are Y/N and never null.",
        "message": "SAFFL is not Y or N.",
        "check": {"all": [{"name": "SAFFL", "operator": "is_not_contained_by", "value": ["Y", "N"]}]},
    },
    {
        "id": "MF-ADAM-003", "domains": ["ADSL"], "variables": ["ITTFL"],
        "description": "The intent-to-treat population flag ITTFL is populated with Y or N for every subject.",
        "citation": "ADaMIG 1.3 Section 3.2.4: subject-level population flags are Y/N and never null.",
        "message": "ITTFL is not Y or N.",
        "check": {"all": [{"name": "ITTFL", "operator": "is_not_contained_by", "value": ["Y", "N"]}]},
    },
    {
        "id": "MF-ADAM-004", "domains": ["ADSL"], "variables": ["SAFFL", "TRTSDT"],
        "description": "Every subject in the safety population has a first treatment date.",
        "citation": "ADaMIG 1.3 Section 3.2.7: TRTSDT is the date of first exposure; safety subjects were exposed.",
        "message": "SAFFL = 'Y' but TRTSDT is missing.",
        "check": {"all": [{"name": "SAFFL", "operator": "equal_to", "value": "Y"}, {"name": "TRTSDT", "operator": "empty"}]},
    },
    {
        "id": "MF-ADAM-005", "domains": ["ALL"], "variables": ["PARAMCD"],
        "description": "PARAMCD is at most 8 characters.",
        "citation": "ADaMIG 1.3 Section 3.3.4: PARAMCD is limited to 8 characters (SAS V5 transport).",
        "message": "PARAMCD is longer than 8 characters.",
        "check": {"all": [{"name": "PARAMCD", "operator": "longer_than", "value": 8}]},
    },
    {
        "id": "MF-ADAM-006", "domains": ["ALL"], "variables": ["PARAMCD", "PARAM"],
        "description": "PARAMCD and PARAM have a one-to-one relationship within a dataset.",
        "citation": "ADaMIG 1.3 Section 3.3.4: there is a one-to-one map between PARAM and PARAMCD.",
        "message": "PARAMCD maps to more than one PARAM.",
        "check": {"all": [{"name": "PARAMCD", "operator": "is_not_unique_relationship", "value": "PARAM"}]},
    },
    {
        "id": "MF-ADAM-007", "domains": ["ALL"], "variables": ["STUDYID", "USUBJID"],
        "description": "Every analysis record identifies its study and subject.",
        "citation": "ADaMIG 1.3 Section 3.1/3.3.1: STUDYID and USUBJID are required in ADSL and BDS.",
        "message": "STUDYID or USUBJID is missing.",
        "check": {"any": [{"name": "STUDYID", "operator": "empty"}, {"name": "USUBJID", "operator": "empty"}]},
    },
    {
        "id": "MF-ADAM-008", "domains": ["ALL"], "variables": ["ANL01FL"],
        "description": "The analysis record flag ANL01FL is Y or null.",
        "citation": "ADaMIG 1.3 Section 3.3.8: record-level analysis flags take Y or null, never N.",
        "message": "ANL01FL is neither Y nor null.",
        "check": {"all": [{"name": "ANL01FL", "operator": "non_empty"}, {"name": "ANL01FL", "operator": "not_equal_to", "value": "Y"}]},
    },
]


def rule_document(rule: dict) -> dict:
    return {
        "Authorities": [{
            "Organization": "Mediforce",
            "Standards": [{
                "Name": "ADaMIG",
                "Version": version,
                "References": [{
                    "Origin": "Mediforce ADaM checks",
                    "Rule Identifier": {"Id": rule["id"], "Version": "1"},
                    "Version": "1.0",
                    "Citations": [{"Cited Guidance": rule["citation"], "Document": "ADaMIG", "Section": rule["citation"].split(":")[0]}],
                }],
            } for version in ("1.3", "1.2", "1.1", "1.0")],
        }],
        "Check": rule["check"],
        "Core": {"Id": rule["id"], "Status": "Draft", "Version": "1"},
        "Description": rule["description"],
        "Executability": "Fully Executable",
        "Outcome": {"Message": rule["message"], "Output Variables": rule["variables"]},
        "Rule Type": "Record Data",
        "Scope": {"Classes": {"Include": ["ALL"]}, "Domains": {"Include": rule["domains"]}},
        "Sensitivity": "Record",
    }


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for stale in TARGET.glob("*.yml"):
        stale.unlink()
    for rule in RULES:
        (TARGET / f"{rule['id']}.yml").write_text(yaml.safe_dump(rule_document(rule), sort_keys=False), encoding="utf-8")
    print(f"wrote {len(RULES)} rules to {TARGET}")


if __name__ == "__main__":
    main()
