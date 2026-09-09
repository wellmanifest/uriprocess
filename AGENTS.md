# URIprocess manufacturing standard

HOME wellmanifest; SHAPE domain_pack. This repository owns normative package
profiles, schemas, conformance fixtures and the read-only reference checker.
Runtime packaging, URIpack execution, Guard, publication adapters and production
routing remain in their runtime repositories. Standard conformance grants no
execution or publication authority.

Record bounded intent before material changes. Use repository-local ticket
worktrees with wellmanifest/worktrees v5 and preserve unknown state. Publish
material changes with tests; use an independently configured Validator for merges.
Initial source publication is not evidence of independent review or deployment.

Documentation ADOPT wellmanifest/docs 0.1.0 at
`fdb0fcaa7c606dc2503cabb71eff64d5f86ee659`, pinned in `.governance/docs.json`.
Canonical information belongs in `docs/information/`, indexed in `docs/README.md`.
Keep declared versions and exact source references. This focused package does
not claim full new-project, DSL, logs or protected CI adoption.

When changing the standard, update VERSION, policy version and bundle digests
in the same material change. Keep supported v1 package schemas compatible or
introduce a new explicit profile. Run `make test` and the pinned Docs checker.
