import timeit
import re

setup_code = """
import re
facts = [
    {"priority": "must", "id": "f1", "value": "10 mg daily 5.5 hours"},
    {"priority": "must", "id": "f2", "value": "Patient age 45 blood pressure 120/80"},
    {"priority": "must", "id": "f3", "value": "No numbers here"},
    {"priority": "must", "id": "f4", "value": "100 200 300 400.5 500"},
    {"priority": "supporting", "id": "f5", "value": "100 200 300 400.5 500"},
    {"priority": "must", "id": "f6", "value": "10 mg daily 5.5 hours 123.456 99"},
] * 10
spoken_by_fact = {
    "f1": ["10 mg daily 5.5 hours"],
    "f2": ["Patient age 45 blood pressure 120/80"],
    "f3": ["No numbers here"],
    "f4": ["100 200 300 400.5 500"],
    "f5": ["100 200 300 400.5 500"],
    "f6": ["10 mg daily 5.5 hours 123.456 99"],
}

NUMERIC_TOKEN_RE = re.compile(r"\\d+(?:[.:]\\d+)*")
"""

test_code_uncompiled = """
for fact in facts:
    if fact["priority"] != "must":
        continue
    spoken = " ".join(spoken_by_fact[fact["id"]])
    missing_numbers = [token for token in re.findall(r"\\d+(?:[.:]\\d+)*", fact["value"]) if token not in spoken]
"""

test_code_compiled = """
for fact in facts:
    if fact["priority"] != "must":
        continue
    spoken = " ".join(spoken_by_fact[fact["id"]])
    missing_numbers = [token for token in NUMERIC_TOKEN_RE.findall(fact["value"]) if token not in spoken]
"""

print("Uncompiled:", timeit.timeit(test_code_uncompiled, setup=setup_code, number=10000))
print("Compiled:", timeit.timeit(test_code_compiled, setup=setup_code, number=10000))
