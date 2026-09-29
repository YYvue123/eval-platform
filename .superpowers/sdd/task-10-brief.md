# Task 10：无损 SchemaForm

Work from E:\eval-platform. Do not create git commits. Do not modify Resources.vue except if SchemaForm API breakage requires a one-line validate() consumer update — prefer keeping Resources.vue for Task 11.

Existing SchemaForm.vue is used by Resources.vue. Keep the v-model / schema props. New validate() returns {ok, missing, errors}; old callers that only use missing still work if you keep missing.

Run frontend commands from E:\eval-platform\frontend.

## Global constraints

- 产品页面文案不写研发口号
- 不创建 commit
- npm run test:unit and npm run build must pass

## Plan text

## Task 10：无损 SchemaForm

**Files:**
- Create: `frontend/src/utils/schemaForm.js`
- Create: `frontend/tests/unit/schemaForm.test.mjs`
- Modify: `frontend/src/components/SchemaForm.vue`
- Modify: `frontend/package.json`

**Interfaces:**
- `buildFields(schema) -> Field[]`
- `applyDefaults(schema, value) -> object`
- `validateValue(definition, value) -> string`
- Component expose: `validate() -> {ok, missing, errors}`

- [ ] **Step 1：写纯函数失败测试**

```javascript
// frontend/tests/unit/schemaForm.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  applyDefaults,
  buildFields,
  validateValue,
} from '../../src/utils/schemaForm.js'

test('integer remains integer and keeps constraints', () => {
  const [field] = buildFields({
    type: 'object',
    properties: {
      count: { type: 'integer', minimum: 1, maximum: 5, default: 2 },
    },
  })
  assert.equal(field.kind, 'integer')
  assert.equal(field.minimum, 1)
  assert.equal(field.maximum, 5)
  assert.equal(field.default, 2)
  assert.match(validateValue(field.definition, 2.5), /整数/)
})

test('defaults initialize missing values without overwriting input', () => {
  const schema = {
    properties: {
      count: { type: 'integer', default: 2 },
      mode: { type: 'string', enum: ['a', 'b'], default: 'a' },
    },
  }
  assert.deepEqual(applyDefaults(schema, { count: 4 }), { count: 4, mode: 'a' })
})

test('validates string pattern and uri format', () => {
  assert.match(validateValue({ type: 'string', pattern: '^a+$' }, 'bbb'), /格式/)
  assert.match(validateValue({ type: 'string', format: 'uri' }, 'not url'), /URL/)
  assert.equal(validateValue({ type: 'string', format: 'uri' }, 'https://a.test'), '')
})

test('marks nested and combinator schemas for advanced JSON', () => {
  const fields = buildFields({
    properties: {
      nested: { type: 'object', properties: { x: { type: 'string' } } },
      choice: { oneOf: [{ type: 'string' }, { type: 'number' }] },
    },
  })
  assert.equal(fields[0].advanced, true)
  assert.equal(fields[1].advanced, true)
})
```

- [ ] **Step 2：加入单测脚本并确认失败**

`package.json`：

```json
"test:unit": "node --test tests/unit/*.test.mjs"
```

Run:

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

Expected: FAIL，`schemaForm.js` 不存在。

- [ ] **Step 3：实现 Schema 纯函数**

`buildFields` 每个 field 保留完整 `definition`，并输出：

```javascript
{
  key, label, description, required, kind,
  enum: definition.enum || [],
  default: definition.default,
  minimum, maximum, exclusiveMinimum, exclusiveMaximum,
  minLength, maxLength, pattern, format,
  advanced: Boolean(
    definition.$ref || definition.oneOf || definition.anyOf ||
    definition.allOf || (definition.type === 'object' && definition.properties)
  ),
}
```

`validateValue`：
- integer 用 `Number.isInteger`；
- number 用 `Number.isFinite`；
- 实现 minimum/maximum/exclusive 边界；
- string 实现长度、pattern、email、uri、date；
- array/object 检查真实类型；
- 空值的 required 检查仍由组件统一处理。

- [ ] **Step 4：组件保留复杂字段原文和错误**

组件新增：

```javascript
const drafts = reactive({})
const fieldErrors = reactive({})

function setComplex(field, text) {
  drafts[field.key] = text
  if (!text.trim()) {
    delete fieldErrors[field.key]
    set(field.key, undefined)
    return
  }
  try {
    const parsed = JSON.parse(text)
    const error = validateValue(field.definition, parsed)
    if (error) {
      fieldErrors[field.key] = error
      return
    }
    delete fieldErrors[field.key]
    set(field.key, parsed)
  } catch (error) {
    fieldErrors[field.key] = jsonErrorMessage(error, text)
  }
}
```

要求：
- 非法 JSON 不调用 `set()`，所以 modelValue 不会变成字符串；
- textarea 绑定 `drafts[field.key]`；
- schema 或 modelValue 变化时，只在没有未解决错误时同步 draft；
- `jsonErrorMessage` 至少返回 `JSON 无效: <message>`；若运行时错误含 position，则计算行号；
- 字段下用 `role="alert"` 显示错误。

- [ ] **Step 5：应用 defaults 与数字限制**

监听 schema，调用 `applyDefaults`，只有结果不同才 emit，避免循环。

integer：

```vue
<el-input-number
  v-else-if="field.kind === 'integer'"
  :model-value="modelValue[field.key]"
  :step="1"
  :precision="0"
  :min="field.minimum"
  :max="field.maximum"
  @update:model-value="set(field.key, $event)"
/>
```

number 不设置 precision；两者均显示边界说明。

- [ ] **Step 6：完善 validate()**

```javascript
validate() {
  const errors = { ...fieldErrors }
  const missing = []
  for (const field of fields.value) {
    const value = props.modelValue[field.key]
    if (field.required && (value === undefined || value === null || value === '')) {
      missing.push(field.key)
      errors[field.key] = '必填'
      continue
    }
    const message = validateValue(field.definition, value)
    if (message) errors[field.key] = message
  }
  Object.assign(fieldErrors, errors)
  return { ok: !missing.length && !Object.keys(errors).length, missing, errors }
}
```

- [ ] **Step 7：运行前端单测与构建**

Run:

```powershell
npm run test:unit
npm run build
```

Expected: 单测 PASS，Vite build 成功。

- [ ] **Step 8：记录文件清单**

记录 Task 10 全部文件。

