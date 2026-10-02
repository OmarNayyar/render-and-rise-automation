# Security and privacy

This repository contains no production credentials, customer data, live Dropbox links, or private queue records.

Keep credentials in a local `.env` file and rotate any secret that is accidentally exposed. Generated `products/`, `data/`, `output/`, reports, logs, OAuth state, delivery links, and queue backups are ignored by Git.

Before publishing changes, inspect staged files with `git diff --cached`, search for credential-like assignments and private URLs, and verify ignored files with `git status --ignored`.
