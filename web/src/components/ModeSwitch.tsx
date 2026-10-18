// The two ways to use the site, always visible in the header: Viewer (recorded runs, nothing is searched) and Lab (search your own words, live).
// Where no Lab server answers, "Lab" leads to the hosted Lab through the wake page; with no hosted Lab linked, it says why it cannot be chosen.
import { PHOTO_BASE } from '../recorded'

export function ModeSwitch({ viewer, canLab, onMode }: { viewer: boolean; canLab: boolean; onMode: (m: 'viewer' | 'lab') => void }) {
  return (
    <div className="mode-switch" role="group" aria-label="How to use the site">
      <button type="button" aria-pressed={viewer} onClick={() => onMode('viewer')}><b>Viewer</b><small>Recorded runs</small></button>
      {canLab
        ? <button type="button" aria-pressed={!viewer} onClick={() => onMode('lab')}><b>Lab</b><small>Try your words</small></button>
        : PHOTO_BASE
          ? <a href="#/wake"><b>Lab ↗</b><small>Try your words</small></a>
          : <button type="button" disabled title="Lab needs a server: see Settings for how to run it"><b>Lab</b><small>needs a server</small></button>}
    </div>
  )
}
