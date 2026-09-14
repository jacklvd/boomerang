import { describe, expect, it } from 'vitest'

import {
  AGENT_TOOLS,
  isAgentTool,
  isStuck,
  logEntry,
  FIXTURE_RUNNING,
  FIXTURE_STUCK,
} from '../src/model/agent-log'
import {
  durableFrom,
  isTerminalOutcome,
  publishable,
  TERMINAL_OUTCOMES,
  FIXTURE_EPHEMERAL,
} from '../src/model/outcome'
import { isReturnState } from '../src/model/vocabulary'

describe('the agent vocabulary is closed', () => {
  it('matches D14 exactly', () => {
    expect([...AGENT_TOOLS]).toEqual([
      'click',
      'select_option',
      'fill',
      'pause_for_user',
      'report_stuck',
      'report_outcome',
    ])
  })

  it('rejects a tool outside it rather than passing it through', () => {
    expect(isAgentTool('click')).toBe(true)
    expect(isAgentTool('navigate')).toBe(false)
    expect(isAgentTool('submit')).toBe(false)
    expect(isAgentTool(undefined)).toBe(false)
  })
})

describe('a log line records the step, never the page', () => {
  /* Frame E1 promises this. A line that quoted the page would put retailer
     text — possibly an address, possibly something the user typed — into a
     record they can screenshot and we might ship in a bug report. */
  it('has nowhere to put a value, a selector or a quotation', () => {
    const entry = logEntry('fill', 'the reason field', 'done')
    expect(Object.keys(entry).sort()).toEqual(['label', 'state', 'target', 'tool'])
  })

  it('writes the label from the tool and target, not from the page', () => {
    expect(logEntry('click', 'the overcoat', 'done').label).toBe('Selected the overcoat')
    expect(logEntry('report_stuck', 'the reason field', 'failed').label).toBe(
      'Could not find the reason field',
    )
  })

  it('carries no page content in either shipped fixture', () => {
    const serialized = JSON.stringify([...FIXTURE_RUNNING, ...FIXTURE_STUCK])
    for (const leaked of ['<', 'http', 'value=', 'class=', 'Alder']) {
      expect(serialized, leaked).not.toContain(leaked)
    }
  })
})

describe('a stuck run is terminal, not slow', () => {
  /* Treating it as "not finished yet" would leave the user watching a spinner
     for a run that already stopped. */
  it('recognises a failed report_stuck', () => {
    expect(isStuck(FIXTURE_STUCK)).toBe(true)
    expect(isStuck(FIXTURE_RUNNING)).toBe(false)
  })

  it('does not call a still-running step stuck', () => {
    expect(isStuck([logEntry('report_stuck', 'the reason field', 'running')])).toBe(false)
  })
})

describe('only the state may be kept', () => {
  it('allows exactly the two v1 outcomes', () => {
    expect([...TERMINAL_OUTCOMES]).toEqual(['qr_ready', 'label_ready'])
    expect(isTerminalOutcome('qr_ready')).toBe(true)
    expect(isTerminalOutcome('handed_to_carrier')).toBe(false)
    expect(isTerminalOutcome('complete')).toBe(false)
  })

  it('uses names the shared return-state vocabulary already has', () => {
    for (const outcome of TERMINAL_OUTCOMES) expect(isReturnState(outcome)).toBe(true)
  })

  /* A raw label or QR artifact is on the never-persisted list, and for a QR
     outcome the server stores only the status. `publishable` takes the whole
     outcome and hands back only the half that may cross. */
  it('hands back a state and a timestamp, and nothing the retailer drew', () => {
    const durable = publishable('qr_ready', FIXTURE_EPHEMERAL, new Date('2026-09-14T06:00:00.500Z'))
    expect(durable).toEqual({ state: 'qr_ready', observedAt: '2026-09-14T06:00:00Z' })

    const serialized = JSON.stringify(durable)
    for (const ephemeral of ['RMA', 'Walgreens', '0.4 mi', 'QR code issued']) {
      expect(serialized, ephemeral).not.toContain(ephemeral)
    }
  })

  it('stamps a timestamp the session parser would accept', () => {
    expect(durableFrom('label_ready', new Date('2026-09-14T06:00:00.123Z')).observedAt).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/,
    )
  })

  /* The ephemeral half describes the artifact; it has no field for the
     artifact. There is nothing to write down by accident. */
  it('has no field for the code itself', () => {
    expect(Object.keys(FIXTURE_EPHEMERAL).sort()).toEqual([
      'artifactAltText',
      'dropOff',
      'dropOffBy',
      'reference',
    ])
    expect(JSON.stringify(FIXTURE_EPHEMERAL)).not.toContain('data:')
  })
})
