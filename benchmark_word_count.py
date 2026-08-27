import re
import timeit

def word_count_old(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))

WORD_COUNT_RE = re.compile(r"\b[\w'-]+\b")

def word_count_new(value: str) -> int:
    return len(WORD_COUNT_RE.findall(value))

test_string = "This is a test string to count words. It has some hyphenated-words and don't." * 10

old_time = timeit.timeit(lambda: word_count_old(test_string), number=10000)
new_time = timeit.timeit(lambda: word_count_new(test_string), number=10000)

print(f"Old time: {old_time:.5f}s")
print(f"New time: {new_time:.5f}s")
print(f"Improvement: {(old_time - new_time) / old_time * 100:.2f}%")
