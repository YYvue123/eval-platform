import test from 'node:test'
import assert from 'node:assert/strict'
import { percentageWeights, validPercentages, reviewText } from '../../src/utils/safetyWorkbench.js'

test('percentage presets distribute rounding across seventeen metrics to exactly 100%', () => {
  const preset = percentageWeights(Object.fromEntries(Array.from({length:17},(_,i)=>[`metric${i}`,1])))
  assert.equal(Object.keys(preset).length,17)
  assert.ok(validPercentages(preset))
  assert.deepEqual(new Set(Object.values(preset)),new Set([5.88,5.89]))
})

test('scenario proportions and zero weights are preserved', () => {
  assert.deepEqual(percentageWeights({risk:1,hallucination:3,alignment:0}),{risk:25,hallucination:75,alignment:0})
  assert.ok(validPercentages({risk:25,hallucination:75}))
  for(const values of [{risk:99},{risk:101,other:-1},{risk:NaN},{}, {risk:null}]) assert.equal(validPercentages(values),false)
  assert.deepEqual(percentageWeights({risk:0}),{})
  assert.deepEqual(percentageWeights({risk:-1,other:3}),{})
})

test('all expert review decisions have Chinese labels', () => {
  assert.equal(reviewText('approved'),'通过')
  assert.equal(reviewText('rejected'),'驳回')
  assert.equal(reviewText('needs_evidence'),'需补证')
})
