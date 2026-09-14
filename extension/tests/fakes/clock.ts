/**
 * An injectable clock. Tests must never sleep, and window derivation is
 * time-dependent, so time is a value the test controls rather than something
 * the environment supplies.
 */
export class FakeClock {
  #now: number

  constructor(start: number | Date = 0) {
    this.#now = start instanceof Date ? start.getTime() : start
  }

  now(): number {
    return this.#now
  }

  date(): Date {
    return new Date(this.#now)
  }

  advance(ms: number): void {
    if (ms < 0) throw new Error('FakeClock cannot go backwards')
    this.#now += ms
  }

  set(to: number | Date): void {
    this.#now = to instanceof Date ? to.getTime() : to
  }
}
