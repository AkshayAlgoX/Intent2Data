import json
from pathlib import Path
from collections import defaultdict
import math
from collections import Counter

def tokenize(text):
    return text.lower().split()

class SimpleBM25:
    def __init__(self, corpus):
        self.doc_len = [len(tokenize(doc)) for doc in corpus]
        self.avgdl = sum(self.doc_len) / max(1, len(corpus))
        self.doc_freqs = []
        self.idf = {}
        self.df = defaultdict(int)
        for doc in corpus:
            tokens = tokenize(doc)
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            for word in freq:
                self.df[word] += 1
        
        N = len(corpus)
        for word, freq in self.df.items():
            self.idf[word] = math.log(1 + (N - freq + 0.5) / (freq + 0.5))
            
    def top_k(self, query, k):
        scores = [0.0] * len(self.doc_freqs)
        q_tokens = tokenize(query)
        k1 = 1.5
        b = 0.75
        for token in q_tokens:
            if token not in self.df: continue
            idf = self.idf[token]
            for i, doc_freq in enumerate(self.doc_freqs):
                tf = doc_freq.get(token, 0)
                if tf == 0: continue
                dl = self.doc_len[i]
                score = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / self.avgdl)))
                scores[i] += score
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [idx for idx, score in ranked[:k]]

metadata_path = Path('../benchmark/HRS_metadata/metadata.jsonl')
raw_vars = []
with open(metadata_path, 'r') as f:
    for line in f:
        raw_vars.append(json.loads(line))

module_to_vars = defaultdict(list)
var_metadata = {}
for v in raw_vars:
    mod = f"{v.get('product_key', '')}::{v.get('section', '')}"
    var_metadata[v['variable_code']] = v
    module_to_vars[mod].append(v)

module_texts = {}
for mod, vars_list in module_to_vars.items():
    text = []
    text.append(vars_list[0].get('product_title', ''))
    text.append(vars_list[0].get('section_title', ''))
    for v in vars_list:
        text.append(v.get('variable_label', ''))
    module_texts[mod] = " ".join(text)

module_list = list(module_texts.keys())
module_docs = [module_texts[m] for m in module_list]
mod_bm25 = SimpleBM25(module_docs)

def validate(q_name, intent, match_terms):
    print(f"\n--- {q_name} ---")
    print(f"Intent: {intent}")
    mod_idxs = mod_bm25.top_k(intent, 5)
    print("Top 5 Modules retrieved:")
    found = False
    for rank, idx in enumerate(mod_idxs):
        mod = module_list[idx]
        print(f"  {rank+1}. {mod}")
        # simulate context filter
        for v in module_to_vars[mod]:
            label = v.get('variable_label', '').lower()
            if any(term in label for term in match_terms):
                print(f"     -> FOUND MATCH in context: {v['variable_code']} | {v['variable_label']}")
                found = True
    if not found:
        print("     -> NO MATCH FOUND IN THESE MODULES")

print("=== Q1: EDUCATION & INCOME ===")
validate("Q1 Exposure", "years of education", ["education"])
validate("Q1 Outcome", "household income", ["income", "earnings"])

print("\n=== Q2: RELIGION & PHYSICAL FUNCTIONING ===")
# Note: we use generic "religion" and "physical functioning" to see if module retrieval works
validate("Q2 Exposure", "lifelong religious spiritual involvement childhood", ["relig", "spirit"])
validate("Q2 Outcome", "physical functioning", ["walking", "bathing", "climb", "functioning"])

print("\n=== Q3: PM2.5 & DEMENTIA ===")
validate("Q3 Exposure", "localized air pollution pm2.5 fine particulate matter exposure", ["pollution", "pm2.5", "air"])
validate("Q3 Outcome", "early onset dementia cognitive impairment", ["dementia", "cognit", "alzheimer"])

