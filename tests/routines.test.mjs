import assert from 'node:assert/strict'
import test from 'node:test'

import { loadPlugin } from './load-plugin.mjs'

// Routine and status handling, where the failure mode is a lie rather than a
// crash: a card that says "Idle" while a routine has been failing for a week is
// worse than no card at all.

test('trusts the gateway scope marker when it is present', () => {
  const { routinesFor } = loadPlugin()

  const routines = routinesFor('researcher', {
    scoped: 'researcher',
    jobs: [
      { job_id: 'a1', name: 'Researcher Digest', schedule: '0 6 * * *', enabled: true },
      { job_id: 'b2', name: 'Unprefixed job', enabled: true }
    ]
  })

  assert.deepEqual(
    routines.map(routine => routine.id),
    ['a1', 'b2']
  )
})

test('falls back to the [bot:name] convention on an unscoped response', () => {
  const { routinesFor } = loadPlugin()

  const routines = routinesFor('researcher', {
    jobs: [
      { job_id: 'a1', name: '[bot:researcher] Digest' },
      { job_id: 'b2', name: 'Someone else’s job' }
    ]
  })

  assert.deepEqual(
    routines.map(routine => [routine.id, routine.name]),
    [['a1', 'Digest']]
  )
})

test('never-run jobs report unknown health, not failure', () => {
  const { routinesFor } = loadPlugin()

  const [routine] = routinesFor('researcher', { scoped: 'researcher', jobs: [{ job_id: 'a1', last_status: null }] })

  assert.equal(routine.lastOk, null)
})

test('reads paused state from any of the fields cron reports it in', () => {
  const { routinesFor } = loadPlugin()

  const routines = routinesFor('bot', {
    scoped: 'bot',
    jobs: [
      { job_id: '1', state: 'paused' },
      { job_id: '2', paused_at: '2026-08-01T00:00:00Z' },
      { job_id: '3', enabled: false },
      { job_id: '4', state: 'scheduled', enabled: true }
    ]
  })

  assert.deepEqual(
    routines.map(routine => routine.paused),
    [true, true, true, false]
  )
})

test('a failure outranks the next scheduled run as the headline', () => {
  const { headlineRoutine } = loadPlugin()

  const headline = headlineRoutine([
    { name: 'soon', nextRun: '2026-08-30T06:00:00Z', paused: false, lastOk: true },
    { name: 'broken', nextRun: '2026-09-01T06:00:00Z', paused: false, lastOk: false }
  ])

  assert.equal(headline.name, 'broken')
})

test('the headline is the soonest run when nothing is broken', () => {
  const { headlineRoutine } = loadPlugin()

  const headline = headlineRoutine([
    { name: 'later', nextRun: '2026-09-05T06:00:00Z', paused: false, lastOk: true },
    { name: 'sooner', nextRun: '2026-08-30T06:00:00Z', paused: false, lastOk: true }
  ])

  assert.equal(headline.name, 'sooner')
})

test('a paused-only bot still gets a headline instead of "none"', () => {
  const { headlineRoutine } = loadPlugin()

  assert.equal(headlineRoutine([{ name: 'held', paused: true, lastOk: null }]).name, 'held')
  assert.equal(headlineRoutine([]), null)
})

test('status ranks a live turn above every other signal', () => {
  const { botStatus } = loadPlugin()

  const status = botStatus({ busy: true, routines: [{ lastOk: false, paused: false }], home: { error: 'broken' } })

  assert.equal(status.kind, 'busy')
})

test('an unreadable Home and a failed routine both demand attention', () => {
  const { botStatus } = loadPlugin()

  assert.equal(botStatus({ home: { error: 'torn write' } }).kind, 'attention')
  assert.equal(botStatus({ routines: [{ lastOk: false, paused: false }] }).kind, 'attention')
  // A paused routine is a choice, not a fault.
  assert.equal(botStatus({ routines: [{ lastOk: false, paused: true }] }).kind, 'idle')
})

test('recent work reads as active, and a stale Home as stale', () => {
  const { botStatus } = loadPlugin()

  const now = 1_800_000_000_000

  assert.equal(botStatus({ lastActive: now / 1000 - 10, now }).kind, 'active')
  assert.equal(botStatus({ lastActive: now / 1000 - 600, now }).kind, 'idle')
  assert.equal(botStatus({ home: { stale: true }, now }).kind, 'stale')
})

test('card summaries describe an absent, broken, and healthy Home differently', () => {
  const { homeSummary } = loadPlugin()

  assert.equal(homeSummary(null), 'none yet')
  assert.equal(homeSummary({ has_home: false }), 'none yet')
  assert.equal(homeSummary({ has_home: true, error: 'bad json' }), 'unreadable')
  assert.equal(homeSummary({ has_home: true, updated_at: '2026-08-29T06:00:00Z' }), 'updated just now')
})
