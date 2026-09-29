# Task 10 实施报告：无损 SchemaForm

## Status

完成。抽出 `buildFields` / `applyDefaults` / `validateValue`，integer 不再被当成 number。
复杂字段用 draft 编辑，非法 JSON 不写回 model。`validate()` 返回 `{ok, missing, errors}`，
`missing` 仍可用。未改 `Resources.vue`，未实现 Task 11–13，未创建 commit。

## TDD 记录

### RED

命令：

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

输出：

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find module
'E:\\eval-platform\\frontend\\src\\utils\\schemaForm.js'
not ok 1 - tests\\unit\\schemaForm.test.mjs
# tests 1
# pass 0
# fail 1
```

失败原因符合预期：`schemaForm.js` 尚不存在。

### GREEN

命令：

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run build
```

`test:unit` 输出：

```text
# tests 4
# pass 4
# fail 0
```

`build` 输出：

```text
✓ 2295 modules transformed.
✓ built in 25.08s
```

Vite production build 成功（含 prebuild 权限收集）。

## What you implemented

- `buildFields`：保留完整 `definition`；`kind` 为 integer/number/enum 等；嵌套 object 与
  oneOf/anyOf/allOf/$ref 标 `advanced`。
- `applyDefaults`：只补缺失键，不覆盖已有值。
- `validateValue`：integer 用 `Number.isInteger`；number 用 `Number.isFinite`；
  边界、pattern、email/uri/date；array/object 检查真实类型；空值不报 required。
- `SchemaForm`：v-model / schema 不变；integer `el-input-number` step=1 precision=0；
  number 无 precision；复杂字段绑定 `drafts`；`role="alert"` 显示错误；
  schema/model 变化且无未解决错误时同步 draft。

## Files

- Create: `frontend/src/utils/schemaForm.js`
- Create: `frontend/tests/unit/schemaForm.test.mjs`
- Modify: `frontend/src/components/SchemaForm.vue`
- Modify: `frontend/package.json`（`test:unit`）

## Concerns

- 组件行为（非法 JSON 不 `set`、draft 同步）没有 Vue 挂载测试，只覆盖纯函数。
- `Resources.vue` 仍只提示 `missing`；校验错误依赖表单内 `role="alert"`，接入在 Task 11。

## Follow-up: sticky validate errors

`validate()` 曾 `const errors = { ...fieldErrors }` 再 `Object.assign`，上次的「必填」不会清掉。
抽出 `collectValidation(fields, values, draftErrors)`：每次按当前值重建 `errors`；仅复杂字段保留未 `set()` 的 draft 错误。
成功 `set()` 会清掉该字段 error。单测：缺 required → `ok` false；写入值后再校验 `ok` true 且该 key 无 error。

命令：`cd frontend; npm run test:unit`

```text
# tests 5
# pass 5
# fail 0
```
