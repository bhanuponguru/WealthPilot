# Security and access

This page describes what the system protects, what it leaves to the deployment, and how to harden an installation.

## Access control

The console has no login. Anyone who can open it can create cases, read every case and record decisions. The default deployment therefore publishes the console on the loopback
address only (`127.0.0.1:8501`). To use it from other machines:

* put it behind a reverse proxy that authenticates users (single sign-on, basic authentication over TLS, a VPN), and
* keep the proxy, not the console, as the only listener exposed to the network.

The reviewer name and authority tier entered in the sidebar are recorded in the audit log but are not authenticated. The approval gate compares the declared tier with the tier the
policy requires; with proxy-level authentication you can map users to tiers before they reach the console.

## Network exposure

| Service | Port | Exposure in the default deployment |
|---|---|---|
| Console | 8501 | Published on `127.0.0.1` |
| Database | 5432 | Published on `127.0.0.1` for local administration; remove the mapping in production |
| Tool servers | 8101-8103 | Internal network only |
| Tracking server | 5000 | Internal network only |
| Embeddings service | 11434 | Internal network only |

Change the database password (`POSTGRES_PASSWORD`) before first start. The model API key is passed to the containers as an environment variable and is never written to the image or to
the database.

## Data handling

* **Protected attributes.** Owner names, addresses and ZIP codes are removed from everything the language model reads (redaction), and a scan rejects memos that contain prohibited-basis terms.
  See [Compliance and human approval](../architecture/compliance.md).
* **Documents.** Uploaded PDFs are stored in the `data` volume under the case number. They are sent to the model service only as text extracted from them, or, for scanned pages, as page images to the
  vision model. Decide whether sending applicant data to a hosted model service is acceptable for your organisation before use.
* **Evidence downloads** never include the sealed identity block.
* **Audit log.** Decisions are appended to a hash-chained log that the History page verifies on every visit. Back it up with the database.
* **Retention.** The case index, checkpoints and uploads grow without limit. Define a retention schedule and purge accordingly; see [Operations](operations.md).

## Hardening checklist

1. Set a strong `POSTGRES_PASSWORD` and do not publish the database port.
2. Front the console with an authenticating proxy and TLS.
3. Encrypt the volumes that hold uploads and the database.
4. Provide the model API key through your secret manager rather than a file in the repository.
5. Back up the database regularly and test a restore.
6. Verify the audit chain on a schedule (`wealthpilot audit-verify`) and store the latest hash outside the database.
7. Review [Known limitations](limitations.md).
