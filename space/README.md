# Lucida Lab (hosted)

A hosted copy of the Lab from the Lucida project (formerly GenKart v2): type a request for an outfit, optionally bring your own model API key for the step that reads your sentence, and see every step of the search with its real time.

- **Catalogue here: all four sources** (about 103,000 products after removing duplicates): Marqo-GS-10M, Kaggle fashion-product-images-small, a Myntra image set and a men's western set.
- **Photos** are small copies: the Marqo ones fetched while the image is built from the Marqo-GS-10M dataset (Apache-2.0 on the dataset card; Zhu et al. 2024, arXiv:2404.08535), the others copied from their Kaggle datasets (declared MIT, PDDL and CC-BY-NC-SA). The photos belong to the sellers; to have one removed, open an issue at https://github.com/Shivb237/lucida/issues.
- **Your API key** is held in memory for one request, sent only to the provider you choose, and never stored or logged. Use a throwaway key with a spend limit anyway.
- Searches are limited to 20 per minute per visitor. The service sleeps when idle, so the first request after a quiet spell can take about 45 seconds.

## Build and deploy (the owner runs these; nothing here runs them automatically)

Needs the local `data/` folder (indexes, titles, thumbnails), Node 22+, and your own `gcloud` sign-in.

1. Assemble the build folder: `scripts/make_space.sh space-build-14` (any new folder name; the script deletes and rebuilds that folder).
2. Build the image: `cd space-build-14 && gcloud builds submit --tag <REGION>-docker.pkg.dev/<PROJECT>/<REPOSITORY>/lab:14 --timeout=3600 .`
   The build checks every package hash and the model revision, so a changed upstream file stops the build instead of changing the search.
3. Put the image tag into `space/cloudrun.yaml`. If the running service uses its own service account (the study's
   Firestore needs one), add `serviceAccountName: <account>` under `spec.template.spec`. `services replace` sets the service to exactly this
   file, so any setting made by hand in the console and missing here is removed. Compare first:
   `gcloud run services describe <SERVICE> --region <REGION> --format export`.
4. Deploy: `gcloud run services replace space/cloudrun.yaml --region <REGION>`.

Keep the service name genkart-lab so the URL does not change.

### Checks after a deploy
- **Ready:** `curl -s https://<URL>/api/ready` answers `{"ready": true, ...}` (503 while loading). `/api/health` only says the process is alive.
- **Cold start:** after 20 or more idle minutes, time the first `curl https://<URL>/api/ready`. Earlier measurements were 36 to 48 s.
- **Per-visitor limit:** from one address, the 21st search within a minute gets 429. Then, from a SECOND network (for example a phone
  hotspot), a search must still succeed straight away. If it gets 429 too, every visitor shares one bucket: the proxy hop count is wrong, so
  set `GENKART_XFF_HOPS` (in `cloudrun.yaml`) to the number of proxies that add an address, and test again.
- **Headers:** `curl -sI https://<URL>/` shows `content-security-policy`, `strict-transport-security` and `x-content-type-options`.
- **API schema hidden:** `https://<URL>/docs` and `/openapi.json` answer 404.

Limits in this image (`space/Dockerfile`): 20 searches a minute per visitor (a search and its plain-search comparison count once), 4 searches
at once per instance, 300 calls with visitors' keys per instance start and 30 an hour per visitor, at most 6 pieces per outfit, request bodies
up to 16 KB, at most 6 instances (`cloudrun.yaml`).

## Study storage (Firestore), only if you run the study

1. Create or choose a Google Cloud project.
2. Enable Firestore in Native mode. Pick the region carefully: it cannot be changed later.
3. Give the Cloud Run runtime service account the role `roles/datastore.user`.
4. Set `serviceAccountName` in `space/cloudrun.yaml`, under `spec.template.spec`.
5. `GENKART_STUDY=firestore` is already set in `cloudrun.yaml`. Nothing to add there.
6. After the deploy, check that `GET /api/health` shows `"study": true`.
7. Share `<run.app URL>/#/study` directly. The static Viewer has no study link.
8. Export the answers: run `gcloud auth login`, then `.venv/bin/python scripts/study_export.py <project-id>`. It writes `data/study/export.jsonl` (git-ignored) and `runs/study.summary.json`. The summary embeds the project id, so review it before committing.
