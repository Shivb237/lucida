// Technical flats: the line drawings designers use for garments. They stand in for product photos in the demo replay only.

export type FlatShape = { d: string; ln: string; st: string }

export const FLATS = {
  camp: { d: 'M40 18 L52 14 L60 22 L68 14 L80 18 L104 34 L96 52 L84 46 L84 106 L36 106 L36 46 L24 52 L16 34 Z', ln: 'M52 14 L60 30 L68 14 M60 30 L60 106', st: 'M40 52 L54 52 L54 66 L40 66 Z M38 100 L82 100' },
  tee: { d: 'M44 16 Q60 28 76 16 L102 30 L94 48 L82 42 L82 106 L38 106 L38 42 L26 48 L18 30 Z', ln: 'M48 18 Q60 32 72 18', st: 'M38 98 L82 98 M26 44 L32 40 M94 44 L88 40' },
  longsl: { d: 'M40 18 L52 14 L60 22 L68 14 L80 18 L92 26 L106 96 L94 98 L84 52 L84 106 L36 106 L36 52 L26 98 L14 96 L28 26 Z', ln: 'M52 14 L60 30 L68 14 M60 30 L60 106', st: 'M15 90 L27 92 M93 92 L105 90' },
  wide: { d: 'M34 10 L86 10 L96 110 L66 110 L60 42 L54 110 L24 110 Z', ln: 'M34 18 L86 18 M60 18 L60 42', st: 'M46 22 L44 64 M74 22 L76 64' },
  shorts: { d: 'M28 30 L92 30 L98 84 L64 88 L60 58 L56 88 L22 84 Z', ln: 'M28 38 L92 38 M60 38 L60 58', st: 'M25 78 L56 82 M64 82 L95 78' },
  chino: { d: 'M38 10 L82 10 L86 110 L64 110 L60 42 L56 110 L34 110 Z', ln: 'M38 18 L82 18 M60 18 L60 42', st: 'M40 24 Q48 30 52 22 M80 24 Q72 30 68 22' },
  loafer: { d: 'M14 76 Q14 58 34 56 L52 64 Q76 66 104 74 Q110 80 104 88 L18 88 Q12 86 14 76 Z', ln: 'M44 62 Q58 72 70 66', st: 'M16 82 L106 82' },
  espa: { d: 'M12 80 Q16 62 40 60 L60 66 Q84 68 106 78 L106 90 L12 90 Z', ln: 'M12 84 L106 84', st: 'M14 87 L104 87 M40 62 Q52 70 64 67' },
  sneaker: { d: 'M12 74 Q14 56 30 54 L46 60 Q60 52 70 60 Q92 64 106 74 L108 88 L12 88 Z', ln: 'M12 80 L108 80', st: 'M48 60 L54 66 M56 58 L62 64 M64 58 L70 64' },
  sandal: { d: 'M14 84 L106 84 L104 92 L16 92 Z', ln: 'M30 84 Q50 56 70 84 M58 84 Q80 60 96 84', st: '' },
  bag: { d: 'M26 46 L94 46 L102 104 L18 104 Z', ln: 'M38 46 Q38 22 60 22 Q82 22 82 46', st: 'M24 60 L96 60 M22 74 L98 74 M20 88 L100 88' },
  hat: { d: 'M10 76 Q60 94 110 76 Q98 66 80 66 Q80 38 60 38 Q40 38 40 66 Q22 66 10 76 Z', ln: 'M41 60 Q60 66 79 60', st: 'M24 72 Q60 84 96 72' },
  belt: { d: 'M8 54 L112 54 L112 68 L8 68 Z', ln: 'M78 50 L94 50 L94 72 L78 72 Z', st: 'M14 58 L74 58 M14 64 L74 64' },
  shades: { d: 'M14 50 Q14 72 34 72 Q50 72 52 54 L68 54 Q70 72 86 72 Q106 72 106 50 Z', ln: 'M52 54 Q60 48 68 54', st: '' },
} satisfies Record<string, FlatShape>

export type FlatName = keyof typeof FLATS

export function FlatPaths({ shape, fill, weight = 1.6 }: { shape: FlatName; fill: string; weight?: number }) {
  const f = FLATS[shape]
  return (
    <>
      <path d={f.d} fill={fill} stroke="var(--ink)" strokeWidth={weight} strokeLinejoin="round" />
      <path d={f.ln} fill="none" stroke="var(--ink)" strokeWidth={weight} strokeLinecap="round" />
      {f.st && <path d={f.st} fill="none" stroke="var(--ink)" strokeWidth={weight * 0.62} strokeDasharray="3 2.6" />}
    </>
  )
}

export function Flat({ shape, fill, label }: { shape: FlatName; fill: string; label: string }) {
  return (
    <svg role="img" aria-label={label} viewBox="0 0 120 120" className="flat">
      <FlatPaths shape={shape} fill={fill} />
    </svg>
  )
}
