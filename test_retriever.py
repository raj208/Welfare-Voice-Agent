import sys
sys.stdout.reconfigure(encoding='utf-8')

from tools.retriever import search_schemes

print(search_schemes("छात्रवृत्ति चाहिए", top_k=3))
