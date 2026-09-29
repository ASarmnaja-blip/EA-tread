"""Move the __main__ block of selector.py to the end of the file (helper)."""
p = "research/foundry/selector.py"
s = open(p, encoding="utf-8").read()
i = s.index('if __name__ == "__main__":')
j = s.find("\ndef ", i)
j = len(s) if j == -1 else j
blk, s = s[i:j], s[:i] + s[j:]
open(p, "w", encoding="utf-8").write(s.rstrip() + "\n\n\n" + blk.strip() + "\n")
