"""HAP field (control) type codes — name <-> numeric type id.

Authoritative source: ``hap worksheet field-types``. This is a baked
copy so the skill ships self-contained; refresh it from that command if
HAP adds types. ``resolve(t)`` accepts a friendly code ("Text"), a
legacy name ("TEXT"), or an int / numeric string and returns the int.
"""
from __future__ import annotations

# code -> numeric type id. Region has variants (19 county / 23 / 24);
# default to 19, override with an explicit int when needed.
CODE_TO_ID: dict[str, int] = {
    "Text": 2, "PhoneNumber": 3, "LandlinePhone": 4, "Email": 5,
    "Number": 6, "Certificate": 7, "Currency": 8, "SingleSelect": 9,
    "MultipleSelect": 10, "Dropdown": 11, "Attachment": 14, "Date": 15,
    "DateTime": 16, "Region": 19, "DynamicLink": 21, "Divider": 22,
    "AmountInWords": 25, "Collaborator": 26, "Department": 27, "Rating": 28,
    "Relation": 29, "Lookup": 30, "Formula": 31, "Concatenate": 32,
    "AutoNumber": 33, "SubTable": 34, "CascadingSelect": 35, "Checkbox": 36,
    "Rollup": 37, "DateFormula": 38, "CodeScan": 39, "Location": 40,
    "RichText": 41, "Signature": 42, "OCR": 43, "Role": 44, "Embed": 45,
    "Time": 46, "Barcode": 47, "OrgRole": 48, "Button": 49, "APIQuery": 50,
    "QueryRecord": 51, "Section": 52, "FunctionFormula": 53, "CustomField": 54,
}

# legacy builder name -> numeric type id (accepted as an alias).
LEGACY_TO_ID: dict[str, int] = {
    "TEXT": 2, "MOBILE_PHONE": 3, "TELEPHONE": 4, "EMAIL": 5, "NUMBER": 6,
    "CRED": 7, "MONEY": 8, "FLAT_MENU": 9, "MULTI_SELECT": 10, "DROP_DOWN": 11,
    "ATTACHMENT": 14, "DATE": 15, "DATE_TIME": 16, "AREA_COUNTY": 19,
    "RELATION": 21, "SPLIT_LINE": 22, "MONEY_CN": 25, "USER_PICKER": 26,
    "DEPARTMENT": 27, "SCORE": 28, "RELATE_SHEET": 29, "SHEET_FIELD": 30,
    "FORMULA_NUMBER": 31, "CONCATENATE": 32, "AUTO_ID": 33, "SUB_LIST": 34,
    "CASCADER": 35, "SWITCH": 36, "SUBTOTAL": 37, "FORMULA_DATE": 38,
    "LOCATION": 40, "RICH_TEXT": 41, "SIGNATURE": 42, "OCR": 43, "EMBED": 45,
    "TIME": 46, "BAR_CODE": 47, "ORG_ROLE": 48, "SEARCH_BTN": 49,
    "SEARCH": 50, "RELATION_SEARCH": 51, "SECTION": 52, "FORMULA_FUNC": 53,
    "CUSTOM": 54,
}

# Type ids that hold a select-style ``options`` list.
SELECT_TYPE_IDS = {9, 10, 11}


def resolve(t) -> int:
    """Return the numeric type id for a code / legacy name / int."""
    if isinstance(t, bool):
        raise ValueError(f"invalid field type: {t!r}")
    if isinstance(t, int):
        return t
    if isinstance(t, str):
        if t.isdigit():
            return int(t)
        if t in CODE_TO_ID:
            return CODE_TO_ID[t]
        if t in LEGACY_TO_ID:
            return LEGACY_TO_ID[t]
    raise ValueError(f"unknown field type: {t!r}")
