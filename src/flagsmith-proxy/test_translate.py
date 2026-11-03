"""Flagsmith mode without Flagsmith: TC-008 items 1 and 2.

1. Every preset command, applied to a model of the Flagsmith environment
   (otelfeature_flagsmith.model), leaves a state that translates back to that
   preset's file: in stage order, from every other preset, and with no
   document to diff against. src/flagd/test_presets.py checks the preset
   files themselves, so this also covers what flagd serves in Flagsmith mode.
2. The translation rules of the entity model (Flagsmith mode), one by one,
   including what is rejected.

Run: make test (in the ci/Dockerfile image; standard library only)
"""

import copy
import json
import sys

from otelfeature_flagsmith import CATALOG, PRESETS, STAGE_ORDER
from otelfeature_flagsmith.model import Environment
from otelfeature_flagsmith.preset import apply_plan, execute, seed_plan
from otelfeature_flagsmith.translate import TranslationError, load_catalog, translate

CAT = load_catalog(CATALOG)


def preset(name):
    return json.loads((PRESETS / f"{name}.json").read_text())


def seeded():
    env = Environment()
    execute(seed_plan(env.document()), env.run)
    return env


def apply(env, name, blind=False):
    plan = apply_plan(name, None if blind else env.document())
    execute(plan, env.run)
    return plan


def check(env, name):
    got = translate(env.document(), CAT)
    assert got == preset(name), f"{name}: translated\n{json.dumps(got, indent=1)}"


def test_stage_order():
    env = seeded()
    for name in STAGE_ORDER + ["03a-weather-boost", "00-baseline"]:
        apply(env, name)
        check(env, name)


def test_every_preset_from_every_preset():
    for start in STAGE_ORDER:
        for target in STAGE_ORDER:
            env = seeded()
            apply(env, start)
            apply(env, target)
            check(env, target)


def test_blind_plan_writes_everything():
    for start in STAGE_ORDER:
        for target in STAGE_ORDER:
            env = seeded()
            apply(env, start)
            apply(env, target, blind=True)
            check(env, target)


def test_plans_write_only_what_differs():
    env = seeded()
    apply(env, "03a-weather-boost")
    plan = apply(env, "03b-incident")
    # The fault, the loop rule's override, the reorder, the marker.
    assert [a[:3] for a in plan] == [
        ["flag", "update", "traceSampleRatio"],
        ["flag", "reorder", "traceSampleRatio"],
        ["flag", "update", "weatherUpstreamFailure"],
        ["flag", "update", "demoPreset"],
    ], plan
    assert apply(env, "03b-incident") == [["flag", "update", "demoPreset", "--value", "03b-incident",
                                           "--type", "string", "--enable"]]


def test_seed_is_repeatable():
    env = seeded()
    execute(seed_plan(env.document()), env.run)
    apply(env, "03-semconv-rules")
    check(env, "03-semconv-rules")


# ── Translation rules ───────────────────────────────────────────────────

def doc_with(segment_rules=None, value="0.1", enabled=True, flag="traceSampleRatio"):
    """03-semconv-rules, with the `production` override replaced."""
    env = seeded()
    apply(env, "03-semconv-rules")
    document = env.document()
    for segment in document["project"]["segments"]:
        if segment["name"] == "production":
            if segment_rules is not None:
                segment["rules"] = segment_rules
            for fs in segment["feature_states"]:
                if fs["feature"]["name"] == flag:
                    fs["feature_state_value"], fs["enabled"] = value, enabled
    return document


def rule(kind, *conditions):
    return {"type": kind, "conditions": [{"operator": op, "property_": prop, "value": value}
                                         for op, prop, value in conditions], "rules": []}


def targeting(document):
    return translate(document, CAT)["flags"]["traceSampleRatio"]["targeting"]["if"][0]


def test_operators():
    cases = {
        "EQUAL": {"==": [{"var": "a.b"}, "x"]},
        "NOT_EQUAL": {"!=": [{"var": "a.b"}, "x"]},
        "GREATER_THAN": {">": [{"var": "a.b"}, 0.5]},
        "GREATER_THAN_INCLUSIVE": {">=": [{"var": "a.b"}, 0.5]},
        "LESS_THAN": {"<": [{"var": "a.b"}, 0.5]},
        "LESS_THAN_INCLUSIVE": {"<=": [{"var": "a.b"}, 0.5]},
    }
    for operator, want in cases.items():
        value = "x" if operator.endswith("EQUAL") and "THAN" not in operator else "0.5"
        got = targeting(doc_with([rule("ALL", (operator, "a.b", value))]))
        assert got == want, (operator, got)


def test_rule_types():
    eq = lambda v: {"==": [{"var": "k"}, v]}
    nested = {"type": "ALL", "conditions": [], "rules": [rule("ANY", ("EQUAL", "k", "1"), ("EQUAL", "k", "2")),
                                                         rule("NONE", ("EQUAL", "k", "3"))]}
    assert targeting(doc_with([nested])) == {"and": [{"or": [eq("1"), eq("2")]}, {"!": eq("3")}]}
    # Two top-level rules are and-ed; nested `and`s are flattened.
    flat = targeting(doc_with([rule("ALL", ("EQUAL", "k", "1")), rule("ALL", ("EQUAL", "k", "2"))]))
    assert flat == {"and": [eq("1"), eq("2")]}, flat


def rejected(document, needle):
    try:
        translate(document, CAT)
    except TranslationError as error:
        assert needle in str(error), (needle, str(error))
        return
    raise AssertionError(f"not rejected: {needle}")


def test_rejections():
    rejected(doc_with([rule("ALL", ("REGEX", "k", ".*"))]), "operator 'REGEX'")
    rejected(doc_with([rule("ALL", ("GREATER_THAN", "k", "high"))]), "needs a number")
    rejected(doc_with([]), "has no rules")
    rejected(doc_with(value="0.3"), "not a variant")
    rejected(doc_with(value="fast"), "not a float")
    rejected(doc_with(enabled=False), "switched off")
    split = doc_with()
    for fs in split["feature_states"]:
        if fs["feature"]["name"] == "telemetryLevel":
            fs["multivariate_feature_state_values"] = [
                {"id": 1, "multivariate_feature_option": {"id": 1, "value": "IO"}, "percentage_allocation": 50}]
    rejected(split, "percentage split")


def test_overrides_added_by_hand_are_deleted():
    env = seeded()
    apply(env, "03-semconv-rules")
    # Overrides demo.json does not list: on a flag without overrides, and on a listed flag.
    for argv in (["flag", "update", "otelEnabled", "--segment", "production", "--disable"],
                 ["flag", "update", "traceSampleRatio", "--segment", "weather-jdbc", "--value", "0.5",
                  "--type", "string", "--enable"]):
        env.run(argv)
    apply(env, "03a-weather-boost")
    check(env, "03a-weather-boost")


def test_feature_states():
    env = seeded()
    apply(env, "03-semconv-rules")
    document = env.document()
    for fs in document["feature_states"]:
        if fs["feature"]["name"] == "telemetryLevel":
            fs["enabled"] = False
    document["feature_states"] = [fs for fs in document["feature_states"]
                                  if fs["feature"]["name"] != "weatherUpstreamFailure"]
    document["feature_states"].append({**copy.deepcopy(document["feature_states"][0]),
                                       "feature": {"id": 99, "name": "somethingElse", "type": "STANDARD"},
                                       "feature_state_value": "REGEX please"})
    flags = translate(document, CAT)["flags"]
    # A non-boolean feature switched off is served disabled; a missing one as in the baseline;
    # an unknown one is ignored.
    assert flags["telemetryLevel"]["state"] == "DISABLED"
    assert flags["weatherUpstreamFailure"] == CAT["flags"]["weatherUpstreamFailure"]
    assert "somethingElse" not in flags


def test_boolean_override_off_is_the_off_variant():
    env = seeded()
    apply(env, "03-semconv-rules")
    record = translate(env.document(), CAT)["flags"]["recordSpan"]
    assert record["targeting"]["if"][1:] == ["off", "on"], record["targeting"]


def main() -> int:
    failures = 0
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
            except AssertionError as error:
                failures += 1
                print(f"FAIL {name}: {error}")
            else:
                print(f"ok   {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
