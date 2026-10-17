# Lucida Lab (hosted)

A hosted copy of the Lab from the Lucida project (formerly GenKart v2): type a request for an outfit, optionally bring your own model API key for the step that reads your sentence, and see every step of the search with its real time.

- **Catalogue here: Marqo only** (about 40,000 products). The full system also searches Kaggle, Myntra and men's western sets, which cannot be redistributed; run the project on your own computer to use them (see the source repository).
- **Photos** are small copies fetched while the image is built from the Marqo-GS-10M dataset (Apache-2.0 on the dataset card; Zhu et al. 2024, arXiv:2404.08535). The photos belong to the sellers; to have one removed, open an issue on the source repository.
- **Your API key** is held in memory for one request, sent only to the provider you choose, and never stored or logged. Use a throwaway key with a spend limit anyway.
- Searches are limited to 20 per minute per visitor. The service sleeps when idle, so the first request after a quiet spell can take about 45 seconds.
