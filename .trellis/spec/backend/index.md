# Backend Code Specs

> Concrete backend implementation contracts for this project.

## Guidelines Index

| Guide | Description | Status |
|---|---|---|
| [RP Core State Block Envelope](./rp-core-state-block-envelope.md) | Read-only Block envelope over RP Core State formal store and compatibility mirrors | Active |

## Pre-Development Checklist

- [ ] Read the relevant backend code-spec file for the module being changed.
- [ ] If the change touches RP memory/Core State, read [RP Core State Block Envelope](./rp-core-state-block-envelope.md).
- [ ] Read shared guides:
  - `.trellis/spec/guides/cross-layer-thinking-guide.md`
  - `.trellis/spec/guides/code-reuse-thinking-guide.md`

## Quality Check

- [ ] New backend contracts have focused unit/integration tests.
- [ ] Cross-layer fields preserve existing identity and source metadata.
- [ ] Migration compatibility mirrors remain intact unless a task explicitly removes them.
- [ ] Lint/format and relevant scoped type checks pass.
