import test from 'node:test'
import assert from 'node:assert/strict'
import {
  applyDefaults,
  buildFields,
  collectValidation,
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

test('collectValidation clears required error after value is applied', () => {
  const fields = buildFields({
    type: 'object',
    required: ['name'],
    properties: { name: { type: 'string' } },
  })
  const sticky = {}
  const first = collectValidation(fields, {}, sticky)
  assert.equal(first.ok, false)
  assert.equal(first.errors.name, '必填')
  Object.assign(sticky, first.errors)
  const second = collectValidation(fields, { name: 'ok' }, sticky)
  assert.equal(second.ok, true)
  assert.equal(second.errors.name, undefined)
  assert.deepEqual(second.errors, {})
})
