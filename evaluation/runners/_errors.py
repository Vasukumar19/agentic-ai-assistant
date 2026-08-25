import json

d = json.load(open('evaluation/results/phase4_full_run_fixed.json', encoding='utf-8'))
fails = [r for r in d['results'] if r.get('primary_failure')]
print('total failures:', len(fails))
for r in fails:
    pf = r['primary_failure']
    ans = (r.get('final_answer') or r.get('error') or '')[:100].replace('\n', ' ')
    seq = r.get('actual_sequence')
    exp = str(r.get('expected_answer'))[:45]
    print(f"[{pf}] {r['id']} | seq={seq} | exp={exp}")
    print(f"    ans: {ans}")

# group by root cause buckets
groups = {}
for r in fails:
    groups.setdefault(r['primary_failure'], []).append(r['id'])
print()
for k, v in sorted(groups.items(), key=lambda x: -len(x[1])):
    print(f"{k} ({len(v)}): {', '.join(v)}")
