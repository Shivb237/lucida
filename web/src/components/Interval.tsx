// One measured value drawn on a real number line: a hatched 95% range, a tick at the average, an optional reference line (zero for a
// difference), gridlines exactly at the axis ticks, and a small arrow where a range runs past the drawn domain (it is clamped, never hidden).
// Positions are percentages of the same domain for the shapes and the axis labels, so the labels always sit on their gridlines.
import { useId } from 'react'

export type Domain = [number, number]

/** A tidy step (1, 2, 2.5 or 5 times a power of ten) giving about `target` intervals over the span. */
export function niceStep(span: number, target = 5) {
  if (!(span > 0)) return 1
  const raw = span / target, p = 10 ** Math.floor(Math.log10(raw)), f = raw / p
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p
}
/** A domain that holds every value given (and anything in `include`, such as zero), widened to whole steps, with its ticks. */
export function niceDomain(values: number[], include: number[] = [], target = 5): { domain: Domain; ticks: number[]; step: number } {
  const all = [...values, ...include].filter((v) => Number.isFinite(v))
  let lo = Math.min(...all), hi = Math.max(...all)
  if (!all.length) { lo = 0; hi = 1 }
  if (lo === hi) { lo -= 0.5; hi += 0.5 }
  const step = niceStep(hi - lo, target)
  const d0 = Math.floor(lo / step + 1e-9) * step, d1 = Math.ceil(hi / step - 1e-9) * step
  return { domain: [round(d0, step), round(d1, step)], ticks: ticksFor([d0, d1], step), step }
}
export function ticksFor(domain: Domain, step = niceStep(domain[1] - domain[0])) {
  const out: number[] = []
  for (let v = domain[0]; v <= domain[1] + step * 1e-6; v += step) out.push(round(v, step))
  return out
}
const round = (v: number, step: number) => { const d = decimals(step); return Number(v.toFixed(d)) }
/** How many decimals the tick labels need: as many as the step itself has. */
export const decimals = (step: number) => { const s = String(Number(step.toPrecision(6))); return s.includes('.') ? Math.min(4, s.split('.')[1].length) : 0 }
const MINUS = '−'
export const fmt = (v: number, d: number, signed = false) => {
  const t = (Math.abs(v) < 0.5 * 10 ** -d ? 0 : v).toFixed(d).replace('-', MINUS)
  return signed && !t.startsWith(MINUS) && Number(t.replace(MINUS, '-')) !== 0 ? `+${t}` : t
}

export function Interval({ domain, ticks, mean, ci, refAt, inUse, old, bar, solid, label, height = 26 }: {
  domain: Domain; ticks: number[]; mean: number | null; ci?: [number, number] | null
  /** where to draw the reference line (zero for a difference) */ refAt?: number | null
  /** the method in use (a picked thing: its tick is magenta) */ inUse?: boolean
  /** superseded: struck through */ old?: boolean
  /** draw a solid bar from the domain start to the value (counts) */ bar?: boolean
  /** draw the solid part below the range (a level, not a difference) */ solid?: boolean
  label: string; height?: number
}) {
  const pid = useId().replace(/:/g, '')
  const [d0, d1] = domain
  const x = (v: number) => ((v - d0) / (d1 - d0)) * 100
  const cl = (v: number) => Math.max(0, Math.min(100, x(v)))
  const lo = ci ? x(ci[0]) : null, hi = ci ? x(ci[1]) : null
  const overL = (lo != null && lo < 0) || (mean != null && x(mean) < 0)
  const overR = (hi != null && hi > 100) || (mean != null && x(mean) > 100)
  const mx = mean != null ? x(mean) : null
  const h = height
  return (
    <svg className="evd-iv" width="100%" height={h} role="img" aria-label={label} overflow="visible">
      <title>{label}</title>
      <defs>
        <pattern id={`h${pid}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
          <rect className="evd-iv-ink" width="1.5" height="6" />
        </pattern>
      </defs>
      <rect className="evd-iv-track" x="0" y="0" width="100%" height={h} />
      {ticks.map((t) => <line key={t} className="evd-iv-grid" x1={`${x(t)}%`} x2={`${x(t)}%`} y1="0" y2={h} />)}
      {bar && mean != null && <rect className="evd-iv-solid" x="0" y="4" width={`${cl(mean)}%`} height={h - 8} />}
      {solid && ci && <rect className="evd-iv-solid" x="0" y="0" width={`${cl(ci[0])}%`} height={h} />}
      {ci && lo != null && hi != null && <rect x={`${cl(ci[0])}%`} y="0" width={`${Math.max(0.4, cl(ci[1]) - cl(ci[0]))}%`} height={h} fill={`url(#h${pid})`} className="evd-iv-ci" />}
      {refAt != null && x(refAt) >= 0 && x(refAt) <= 100 && <line className="evd-iv-ref" x1={`${x(refAt)}%`} x2={`${x(refAt)}%`} y1={-5} y2={h + 5} />}
      {!bar && mx != null && mx >= 0 && mx <= 100 && <rect className={inUse ? 'evd-iv-tick in-use' : 'evd-iv-tick'} x={`${mx}%`} transform="translate(-1.5 0)" y={-6} width="3" height={h + 12} />}
      {overL && <svg x="0" y="0" width="1" height={h} overflow="visible"><path className="evd-iv-over" d={`M9 ${h / 2 - 6} L1 ${h / 2} L9 ${h / 2 + 6} Z`} /></svg>}
      {overR && <svg x="100%" y="0" width="1" height={h} overflow="visible"><path className="evd-iv-over" d={`M-9 ${h / 2 - 6} L-1 ${h / 2} L-9 ${h / 2 + 6} Z`} /></svg>}
      {old && <line className="evd-iv-strike" x1="-6" x2="100%" y1={h / 2} y2={h / 2} />}
    </svg>
  )
}

/** The labels under a column of intervals, placed at the same percentages as the gridlines (the end labels are pulled inside). */
export function Axis({ domain, ticks, digits, signed }: { domain: Domain; ticks: number[]; digits: number; signed?: boolean }) {
  const [d0, d1] = domain
  return (
    <div className="evd-axis mono" aria-hidden="true">
      {ticks.map((t, i) => {
        const left = ((t - d0) / (d1 - d0)) * 100
        const shift = i === 0 ? '0' : i === ticks.length - 1 ? '-100%' : '-50%'
        return <span key={t} style={{ left: `${left}%`, transform: `translateX(${shift})` }}>{fmt(t, digits, signed)}</span>
      })}
    </div>
  )
}
