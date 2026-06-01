# ADR-0011: RP services import lint

- **状态（Status）**: Accepted
- **日期（Date）**: 2026-06-01
- **来源（Source）**: `.trellis/spec/backend/rp-services-organization-contract.md` §4；`.trellis/tasks/05-29-t8-t26-rp-services-lint/research/t26-import-lint-explore-2026-06-01.md`；T8 先例 `backend/rp/devtools/check_service_sizes.py` 与 `.pre-commit-config.yaml`

## 背景（Context）

`backend/rp/services/` 已按 10 个领域子目录组织，组织契约 §4 要求：

- 同一服务子目录内的 peer import 使用 `from .<peer> import X`；
- 服务子目录之间优先使用 `from ..<domain>.<module> import X`，absolute `rp.services.<domain>.<module>` 仍可接受；
- `services/` 外部调用者必须使用 absolute `rp.services.<domain>.<module>`；
- T2 后旧 shim basename 路径不得重新出现；
- 跨领域绕过 facade 的直接导入目前只能作为 review 候选，不能机械判定全部错误。

T26 explore 比较了 `import-linter`、Flake8 plugin、Ruff custom rule 与本地 AST checker。结论是：T26 第一阶段要约束的是 import 源码形状，而不是单纯的模块依赖图。`import-linter` 很适合表达 forbidden/protected/layers 等依赖图契约，但它看不出同一条边是写成 `from .service` 还是 `from rp.services.retrieval.service`。Ruff 当前不支持项目自定义 lint rule 或第三方 plugin。Flake8 plugin 可行，但会引入新的 lint 栈和依赖。

T8 已经落地了无新依赖的本地 AST checker 加 local pre-commit hook，证明该模式能表达 RP services 专属契约，并能在后续 CI 中复用同一命令。

## 决策（Decision）

我们采用 **custom AST checker + local pre-commit hook** 作为 T26 第一阶段 import lint：

- 新增 `backend/rp/devtools/check_service_imports.py`，递归扫描 `backend/**/*.py` 与实际 `backend/rp/services/<domain>/<module>.py` domain map，不引入新依赖。
- 在 `.pre-commit-config.yaml` 的 T8 `rp-service-size-lint` 后新增 `rp-service-import-lint`，使用 `language: system`、`pass_filenames: false`、`require_serial: true`，由 checker 扫描完整 backend import contract。
- hard-fail 只覆盖机械可判定且当前应保持 0 baseline 的规则：
  - 服务同子目录 peer 使用 absolute `rp.services.<same_domain>.<module>`；
  - 服务内 `from ..<root_module>` 等非 domain/root-level relative import；
  - T2 后旧 shim basename 形态，即 `rp.services.<old_basename>` 或服务内指向不存在 peer 的 `from .<old_basename>`；
  - `services/` 外部对 RP services 的 relative 或非具体模块导入。
- report-only 覆盖尚未适合 gate 的规则：
  - 服务内跨子目录 absolute imports 仅报告，不 fail；
  - facade-bypass candidates 仅按目标 domain/module 分组报告，不 fail。
- checker 预留 `--strict-facade-bypass` 参数，但默认关闭；只有未来定义了各 domain 的明确 public surface 后，才能把候选提升为 ratchet gate。

## 影响（Consequences）

- 正向：T26 能立刻防止同目录 absolute import、旧 shim 路径和外部相对服务导入回潮；T6 拆分出的新 retrieval broker 文件会被同一规则保护。
- 正向：不增加 `backend/requirements.txt` 依赖，Windows/local/pre-commit/未来 CI 使用同一命令，维护面与 T8 保持一致。
- 代价：checker 是项目专属代码，需要本仓维护测试覆盖，而不是外部 lint 工具直接承包。
- 代价：跨子目录 absolute imports 仍会存在一段时间；本 ADR 明确它们是 advisory，不在 T26 批量重写，避免与 T6 broker decomposition 和其他领域重构互相制造 churn。
- 约束：facade-bypass 目前只是候选报告；若未来要 hard-fail，必须先新增或修订 ADR/spec，定义每个 domain 的 public import surface，并用 baseline/ratchet 路径逐步收紧。
