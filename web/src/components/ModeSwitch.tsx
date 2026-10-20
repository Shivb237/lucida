// The two ways to use the site, always in the header: Replay (recorded runs, nothing is searched) and Try it live (search your own words).
// Where no live server answers here, "Try it live" leads to the hosted Lab through the wake page; with no hosted Lab linked, it says in words why it cannot be chosen.
import { PHOTO_BASE } from '../recorded'

export function ModeSwitch({ viewer, canLab, onMode }: { viewer: boolean; canLab: boolean; onMode: (m: 'viewer' | 'lab') => void }) {
  return (
    <div className="mode-switch" role="group" aria-label="How to use the site">
      <button type="button" aria-pressed={viewer} onClick={() => onMode('viewer')}><b>Replay</b><small>recorded runs</small></button>
      {canLab
        ? <button type="button" aria-pressed={!viewer} onClick={() => onMode('lab')}><b>Try it live</b><small>your own words</small></button>
        : PHOTO_BASE
          ? <a href="#/wake"><b>Try it live <span aria-hidden="true">↗</span></b><small>wakes a server, about 45 s</small></a>
          : <button type="button" disabled aria-describedby="live-why"><b>Try it live</b><small id="live-why">needs a server: see How it works</small></button>}
    </div>
  )
}
