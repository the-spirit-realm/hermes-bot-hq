import assert from 'node:assert/strict'
import test from 'node:test'

import { loadPlugin } from './load-plugin.mjs'

// Actions are the only place a Home reaches out of its own page, so each one
// must resolve to exactly the operation it names — and a failure must be
// reported rather than swallowed into a button that looks like it worked.

test('run_routine goes through the plugin backend and refreshes the page', async () => {
  const plugin = loadPlugin({
    restResults: { '/home/researcher/run-routine': { ok: true, name: 'Digest', executed: true } }
  })

  await plugin.performAction('researcher', { id: 'r', label: 'Run now', type: 'run_routine', job: 'Digest' })

  assert.deepEqual(plugin.restCalls[0].path, '/home/researcher/run-routine')
  assert.equal(plugin.restCalls[0].opts.method, 'POST')
  assert.deepEqual(plugin.restCalls[0].opts.body, { job: 'Digest' })
  assert.equal(plugin.notifications[0].kind, 'success')
  assert.ok(plugin.invalidations.length)
})

test('a backgrounded run says so instead of claiming it finished', async () => {
  const plugin = loadPlugin({
    restResults: { '/home/bot/run-routine': { ok: true, name: 'Digest', background: true } }
  })

  await plugin.runRoutine('bot', 'Digest')

  assert.match(plugin.notifications[0].message, /background/)
})

test('open_url and open_path use the OS door, not a navigation', async () => {
  const plugin = loadPlugin()

  await plugin.performAction('bot', { id: 'u', label: 'Docs', type: 'open_url', url: 'https://example.com' })
  await plugin.performAction('bot', { id: 'p', label: 'Notes', type: 'open_path', path: '/tmp/notes.md' })

  assert.deepEqual(plugin.opened, ['https://example.com'])
  assert.deepEqual(plugin.revealed, ['/tmp/notes.md'])
  assert.deepEqual(plugin.notifications, [])
})

test('a refused OS call warns instead of failing silently', async () => {
  const plugin = loadPlugin({ openExternal: false, revealPath: false })

  await plugin.performAction('bot', { id: 'u', label: 'Docs', type: 'open_url', url: 'https://example.com' })
  await plugin.performAction('bot', { id: 'p', label: 'Notes', type: 'open_path', path: '/tmp/gone.md' })

  assert.deepEqual(
    plugin.notifications.map(entry => entry.kind),
    ['warning', 'warning']
  )
})

test('open_chat reuses the canonical Bot Chat when one exists', async () => {
  const plugin = loadPlugin({
    requestResults: {
      'profiles.list': {
        profiles: [{ name: 'researcher', canonical_session: { id: 'chat-1' }, last_session: { id: 'chat-2' } }]
      }
    }
  })

  await plugin.performAction('researcher', { id: 'c', label: 'Open chat', type: 'open_chat' })

  assert.deepEqual(plugin.sessionOpens, [{ id: 'chat-1', options: { profile: 'researcher' } }])
  assert.deepEqual(plugin.newChats, [])
})

test('open_chat starts a conversation for a bot that has none', async () => {
  const plugin = loadPlugin({ requestResults: { 'profiles.list': { profiles: [{ name: 'writer' }] } } })

  await plugin.performAction('writer', { id: 'c', label: 'Open chat', type: 'open_chat' })

  assert.deepEqual(plugin.newChats, ['writer'])
  assert.deepEqual(plugin.sessionOpens, [])
})

test('an unknown action type does nothing at all', async () => {
  const plugin = loadPlugin()

  await plugin.performAction('bot', { id: 'x', label: 'Danger', type: 'shell', command: 'rm -rf /' })

  assert.deepEqual(plugin.requests, [])
  assert.deepEqual(plugin.restCalls, [])
  assert.deepEqual(plugin.opened, [])
  assert.deepEqual(plugin.revealed, [])
})

test('the composer sends to the bot Chat and reports a refusal', async () => {
  const plugin = loadPlugin({ requestResults: { 'cli.exec': { blocked: false, code: 0, output: 'done' } } })

  await plugin.sendPrompt('researcher', 'refresh the numbers')

  const [call] = plugin.requests

  assert.equal(call.method, 'cli.exec')
  assert.deepEqual(call.params.argv, [
    '-p',
    'researcher',
    'chat',
    '-c',
    'Bot Chat',
    '--create-if-missing',
    '-Q',
    '--query',
    'refresh the numbers'
  ])

  const blocked = loadPlugin({ requestResults: { 'cli.exec': { blocked: true, hint: 'not headless' } } })

  await assert.rejects(() => blocked.sendPrompt('bot', 'hi'), /not headless/)

  const failed = loadPlugin({ requestResults: { 'cli.exec': { blocked: false, code: 1, output: 'boom' } } })

  await assert.rejects(() => failed.sendPrompt('bot', 'hi'), /boom/)
})
