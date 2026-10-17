# Lucida Lab (hosted)

A hosted copy of the Lab from the Lucida project (formerly GenKart v2): type a request for an outfit, optionally bring your own model API key for the step that reads your sentence, and see every step of the search with its real time.

- **Catalogue here: all four sources** (about 103,000 products after removing duplicates): Marqo-GS-10M, Kaggle fashion-product-images-small, a Myntra image set and a men's western set.
- **Photos** are small copies: the Marqo ones fetched while the image is built from the Marqo-GS-10M dataset (Apache-2.0 on the dataset card; Zhu et al. 2024, arXiv:2404.08535), the others copied from their Kaggle datasets (declared MIT, PDDL and CC-BY-NC-SA). The photos belong to the sellers; to have one removed, open an issue at https://github.com/Shivb237/lucida/issues.
- **Your API key** is held in memory for one request, sent only to the provider you choose, and never stored or logged. Use a throwaway key with a spend limit anyway.
- Searches are limited to 20 per minute per visitor. The service sleeps when idle, so the first request after a quiet spell can take about 45 seconds.
