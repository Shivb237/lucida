// "How it got there": the six steps of one run as a vertical stepper. Each closed card says, in one plain sentence, what that step did
// (content/story.ts), with its seconds and its density mark; opening it shows the full account and the technical panel for that step.
import { useState, type ReactNode } from 'react'
import { narrateSteps } from '../content/story'
import { MARK_CLASS, STATUS_WORD, STEPS, type StageId, type StepState } from '../trace'
import { fmt } from '../ui'

export function Stepper({ steps, detail, demo = false, after }: { steps: Record<StageId, StepState>; detail: Partial<Record<StageId, ReactNode>>; demo?: boolean; after?: ReactNode }) {
  const told = narrateSteps(steps)
  const [open, setOpen] = useState<Set<StageId>>(() => new Set())
  const allOpen = open.size === STEPS.length
  const toggle = (id: StageId, on: boolean) => setOpen((prev) => {
    if (prev.has(id) === on) return prev
    const next = new Set(prev)
    if (on) next.add(id); else next.delete(id)
    return next
  })
  return (
    <section id="how" aria-labelledby="how-h" className="stepper">
      <div className="sec-top">
        <p className="lg dim layer-label">What Lucida shows an engineer</p>
        <h2 id="how-h" className="sec-h">How it got there</h2>
        <button type="button" className="btn-line" aria-controls="how-steps" onClick={() => setOpen(allOpen ? new Set() : new Set(STEPS.map((s) => s.id)))}>
          {allOpen ? 'Close all steps' : 'Open all steps'}
        </button>
      </div>
      <p className="sec-lead">Six steps, in order. Open one to see exactly what it did.</p>
      <ol id="how-steps" className="steps">
        {STEPS.map((s, i) => {
          const v = steps[s.id]
          const t = told[s.id]
          const timed = v.status === 'done' || v.status === 'failed'
          return (
            <li key={s.id} className="step" data-status={v.status}>
              <details open={open.has(s.id)} onToggle={(e) => toggle(s.id, (e.currentTarget as HTMLDetailsElement).open)}>
                <summary>
                  <span className={`tile ${MARK_CLASS[v.status]}`} aria-hidden="true" />
                  <span className="step-main">
                    <span className="step-name">{i + 1}. {s.name}{demo ? ' (demo)' : ''}</span>
                    <span className="step-line">{t.headline}</span>
                  </span>
                  <span className="step-meta">
                    <span className="mono step-sec">{timed && v.seconds != null ? `${fmt(v.seconds, 2)} s` : '—'}</span>
                    <span className="lg dim">{STATUS_WORD[v.status]}</span>
                  </span>
                </summary>
                <div className="step-body">
                  <p className="step-explain"><span className="lg dim">What this step does</span> {s.explain}</p>
                  {t.lines.length > 0 && t.status !== 'not run' && t.status !== 'started' && (
                    <div className="step-lines">{t.lines.map((l, k) => <p key={k}>{l}</p>)}</div>
                  )}
                  {detail[s.id]}
                </div>
              </details>
            </li>
          )
        })}
      </ol>
      {after}
    </section>
  )
}
