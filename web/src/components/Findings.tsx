// The claim cards of the Evidence page, in page order. Each card is built from one claim in virtual:evidence (question, computed verdict,
// effects with their 95% ranges, method, limits, sources, exact tables); a page can add extra content to a card by its id (the drawings).
import type { ReactNode } from 'react'
import type { Claim, ClaimId } from 'virtual:evidence'
import { Card } from './EvidenceKit'

export type CardExtras = Partial<Record<ClaimId, { extra?: ReactNode; exact?: ReactNode }>>

export function Findings({ claims, extras = {} }: { claims: Claim[]; extras?: CardExtras }) {
  return <>{claims.map((c) => <Card key={c.id} claim={c} extra={extras[c.id]?.extra} exact={extras[c.id]?.exact} />)}</>
}
