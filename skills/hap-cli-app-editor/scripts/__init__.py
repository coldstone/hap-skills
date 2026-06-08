"""hap-cli-app-editor — fine-grained CRUD over individual HAP elements.

This package is fully self-contained and shares no code with the
hap-cli-app-creator skill, so the two skills can be distributed
independently. It drives the installed ``hap`` CLI to read an app's live
structure, then applies a structured *edit-spec* (validate -> plan ->
apply) against single elements (worksheets, fields, views, roles,
custom actions, workflows, custom pages, components).

Run as ``python3 -m scripts <validate|plan|apply|inspect|selftest>`` from
the skill directory.
"""
