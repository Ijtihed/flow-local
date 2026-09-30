# Contributing

Open an issue describing the problem, OS, Flow version and steps to reproduce. Remove names, API keys, GitHub tokens and personal transcripts from screenshots or logs. The app's speech report uses bundled synthetic test audio; review a report before attaching it.

For changes, install `requirements.txt` in a virtual environment, run `python -m unittest discover -s tests -v`, then `npm ci --prefix tests` and `node tests/interface.cjs`. Windows and Ubuntu CI also run known-audio speech regression. See the README for build and Linux platform limitations.

Keep runtime data, downloaded models and credentials out of commits. Preserve the existing interface style, accessible controls and reduced-motion behavior. App logos identify third-party products and belong to their respective owners; see `assets/logos/SOURCES.txt`.

Publishing requires a new unused version from `python tools/release_version.py VERSION`. The Publish update workflow tests both platforms before creating a completed release. Never replace a published installer under an existing version.
