# RAG Retrieval Evaluation

`retrieval_cases.json`은 관리된 Knowledge Corpus에 대한 semantic retrieval Ground Truth 데이터셋입니다.
평가 단위는 사용자 자연어 질의이며, 각 case는 최소 한 개의 expected document id를 가집니다.

초기 Gate:
- Hit Rate@5 >= 0.90
- Mean Recall@5 >= 0.90
- MRR >= 0.70
- Metadata Filter Accuracy >= 0.95

Generation answer grounding / citation correctness는 Agent와 RAG를 연결한 이후 별도 평가합니다.
