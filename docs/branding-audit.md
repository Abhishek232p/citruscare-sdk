# Branding and source-reference audit

The project identity is CitrusCare SDK (`citruscare-sdk`; Python import
`citruscare`). No source implementation was copied from the public reference
repository. This search is case-insensitive and covers tracked project files,
excluding Git metadata and generated files. The source/reference terms audited
were `eka-care`, `Eka`, `eka`, and `echo-sdk`.

## Remaining occurrences

| File | Classification | Reason |
| --- | --- | --- |
| `THIRD_PARTY_NOTICES.md` | Required license attribution and source reference | Records the MIT copyright/permission notice seen in the reference repository. No source code is claimed as included. |
| `README.md` | Third-party reference | Identifies the repository consulted for architecture and points to its preserved notice. |
| `docs/branding-audit.md` | Audit documentation | Names the search terms and classifies the remaining legal/reference matches; these are not product branding. |

Any occurrence outside those documented legal/reference locations is obsolete
branding and should be removed or reviewed before publication. Repeat the
case-insensitive search after changes to dependencies, documentation, or
examples.
