import assert from 'node:assert/strict'
import test from 'node:test'

import { loadPlugin } from './load-plugin.mjs'

// Widget rendering helpers. Everything here is fed by model-authored JSON, so
// the tests care most about the degenerate shapes: empty payloads, one-point
// series, flat lines, and markdown that is really just prose.

test('markdown splits into paragraphs and bullet runs', () => {
  const { markdownBlocks } = loadPlugin()

  const blocks = markdownBlocks('First line.\nStill first.\n\n- one\n- two\n\nLast.')

  assert.deepEqual(
    blocks.map(block => block.kind),
    ['p', 'ul', 'p']
  )
  assert.deepEqual(blocks[1].lines, ['one', 'two'])
})

test('a mixed block stays prose rather than becoming a half-list', () => {
  const { markdownBlocks } = loadPlugin()

  const blocks = markdownBlocks('Summary:\n- one')

  assert.equal(blocks.length, 1)
  assert.equal(blocks[0].kind, 'p')
})

test('empty markdown produces no blocks', () => {
  const { markdownBlocks } = loadPlugin()

  assert.deepEqual(markdownBlocks(''), [])
  assert.deepEqual(markdownBlocks('   \n\n  '), [])
})

test('a sparkline maps points into the viewBox with y inverted', () => {
  const { sparklinePath } = loadPlugin()

  const path = sparklinePath([
    [0, 0],
    [10, 100]
  ])

  // First point is the minimum, so it sits at the BOTTOM (y=100) and the
  // rising second point at the top — a rising series must rise on screen.
  assert.equal(path, 'M0.00 100.00 L100.00 0.00')
})

test('a flat series still draws instead of dividing by zero', () => {
  const { sparklinePath } = loadPlugin()

  const path = sparklinePath([
    [0, 5],
    [1, 5]
  ])

  assert.ok(path.startsWith('M'))
  assert.ok(!path.includes('NaN'))
})

test('fewer than two points draws nothing', () => {
  const { sparklinePath } = loadPlugin()

  assert.equal(sparklinePath([[0, 1]]), '')
  assert.equal(sparklinePath([]), '')
  assert.equal(sparklinePath(undefined), '')
})

test('emptiness is per widget type, so a blank card never looks confident', () => {
  const { widgetHasContent } = loadPlugin()

  assert.equal(widgetHasContent('kpi', { items: [] }), false)
  assert.equal(widgetHasContent('kpi', { items: [{ label: 'x' }] }), true)
  assert.equal(widgetHasContent('table', { columns: ['a'], rows: [] }), false)
  assert.equal(widgetHasContent('table', { columns: ['a'], rows: [['1']] }), true)
  assert.equal(widgetHasContent('markdown', { text: '   ' }), false)
  assert.equal(widgetHasContent('markdown', { text: 'hi' }), true)
  // One point cannot be plotted, so the widget is empty, not broken.
  assert.equal(widgetHasContent('timeseries', { series: [{ points: [[0, 1]] }] }), false)
  assert.equal(widgetHasContent('timeseries', { series: [{ points: [[0, 1], [1, 2]] }] }), true)
  assert.equal(widgetHasContent('list', null), false)
})

test('numbers stay readable at both ends of the scale', () => {
  const { formatNumber } = loadPlugin()

  assert.equal(formatNumber(1234567), (1234567).toLocaleString())
  assert.equal(formatNumber(3.14159), '3.14')
  assert.equal(formatNumber('nope'), '')
})

test('routine summaries name the state, not just the routine', () => {
  const { routineSummary } = loadPlugin()

  assert.equal(routineSummary(null), 'none')
  assert.equal(routineSummary({ name: 'digest', paused: true }), 'digest (paused)')
  assert.equal(routineSummary({ name: 'digest', lastOk: false }), 'digest — failed')
  assert.equal(routineSummary({ name: 'digest', nextRun: '2026-08-30T06:00:00Z' }), 'digest · just now')
})

test('ISO timestamps are converted before relativeTime runs', () => {
  const { toEpochMs, when } = loadPlugin()

  assert.ok(Number.isFinite(toEpochMs('2026-08-30T06:00:00Z')))
  assert.equal(when('2026-08-30T06:00:00Z'), 'just now')
  assert.equal(when('not-a-date', 'fallback'), 'fallback')
})
