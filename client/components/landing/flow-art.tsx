/* Small diagrammatic illustrations for the "How it works" strip. Deliberately
   schematic — they show the shape of the flow, not a screenshot of it. */

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-31 w-full rounded-xl bg-bg">
      <svg viewBox="0 0 200 124" className="h-full w-full" role="presentation">
        {children}
      </svg>
    </div>
  )
}

function Window({ children }: { children: React.ReactNode }) {
  return (
    <>
      <rect x="26" y="20" width="148" height="86" rx="8" fill="#fff" stroke="#E3DED4" />
      <path d="M26 28a8 8 0 0 1 8-8h132a8 8 0 0 1 8 8v6H26z" fill="#F1ECE3" />
      <circle cx="37" cy="27" r="2.5" fill="#E3DED4" />
      <circle cx="45" cy="27" r="2.5" fill="#E3DED4" />
      <circle cx="53" cy="27" r="2.5" fill="#E3DED4" />
      {children}
    </>
  )
}

const cursor = (x: number, y: number) => (
  <path
    d={`M${x} ${y}l0 15 3.6-3.6 2.4 5.2 2.6-1.2-2.4-5.2 5 -0.6z`}
    fill="#1A1917"
    stroke="#fff"
    strokeWidth="1.2"
  />
)

/** 01 — you open your orders page */
export const ArtOpenOrders = () => (
  <Frame>
    <Window>
      {[0, 1, 2].map((i) => (
        <g key={i}>
          <rect x="36" y={44 + i * 20} width="16" height="16" rx="4" fill="#E6E0D5" />
          <rect x="58" y={47 + i * 20} width={72 - i * 14} height="4" rx="2" fill="#D8D2C6" />
          <rect x="58" y={55 + i * 20} width={44 - i * 8} height="4" rx="2" fill="#EBE6DC" />
        </g>
      ))}
    </Window>
    {cursor(126, 74)}
  </Frame>
)

/** 02 — we rank what is closing */
export const ArtRank = () => (
  <Frame>
    {[
      { w: 104, fill: '#B33517', soft: '#FBE7E1' },
      { w: 78, fill: '#8E5E06', soft: '#FBF0DA' },
      { w: 56, fill: '#387046', soft: '#E5F0E7' },
    ].map((row, i) => (
      <g key={i}>
        <rect x="30" y={30 + i * 24} width="140" height="18" rx="9" fill="#fff" stroke="#E3DED4" />
        <rect x="30" y={30 + i * 24} width={row.w} height="18" rx="9" fill={row.soft} />
        <circle cx={row.w + 20} cy={39 + i * 24} r="4" fill={row.fill} />
      </g>
    ))}
    <path d="M34 100 L 96 88 L 166 68" stroke="#0C6E6B" strokeWidth="2" fill="none" />
    <circle cx="166" cy="68" r="4" fill="#0C6E6B" />
  </Frame>
)

/** 03 — one click starts the return */
export const ArtOneClick = () => (
  <Frame>
    <Window>
      <rect x="38" y="44" width="96" height="4" rx="2" fill="#D8D2C6" />
      <rect x="38" y="54" width="64" height="4" rx="2" fill="#EBE6DC" />
      <rect x="38" y="70" width="60" height="22" rx="7" fill="#0C6E6B" />
      <rect x="104" y="70" width="46" height="22" rx="7" fill="#fff" stroke="#E3DED4" />
      <circle cx="68" cy="81" r="17" fill="none" stroke="#5FB8B4" strokeWidth="1.5" opacity="0.7" />
    </Window>
    {cursor(64, 78)}
  </Frame>
)

/** 04 — label printed, box collected */
export const ArtPickup = () => (
  <Frame>
    <rect x="18" y="98" width="164" height="2" rx="1" fill="#E3DED4" />
    <g fill="#0C6E6B">
      <rect x="96" y="52" width="52" height="30" rx="4" />
      <path d="M148 62h14l10 12v8h-24z" />
      <circle cx="112" cy="88" r="8" fill="#1A1917" />
      <circle cx="160" cy="88" r="8" fill="#1A1917" />
    </g>
    <rect x="30" y="58" width="52" height="40" rx="4" fill="#E6E0D5" />
    <rect x="53" y="58" width="6" height="40" fill="#D8D2C6" />
    <rect x="36" y="64" width="30" height="22" rx="2" fill="#fff" />
    <rect x="39" y="67" width="20" height="2.5" rx="1" fill="#D8D2C6" />
    <rect x="39" y="72" width="14" height="2.5" rx="1" fill="#EBE6DC" />
    {[0, 1, 2, 3, 4, 5, 6].map((i) => (
      <rect key={i} x={39 + i * 4} y="78" width={i % 2 ? 1.4 : 2.4} height="6" fill="#1A1917" />
    ))}
  </Frame>
)

/** 05 — reminder on your calendar */
export const ArtCalendar = () => (
  <Frame>
    <rect x="46" y="30" width="108" height="76" rx="8" fill="#fff" stroke="#E3DED4" />
    <path d="M46 38a8 8 0 0 1 8-8h92a8 8 0 0 1 8 8v10H46z" fill="#0C6E6B" />
    <rect x="70" y="22" width="5" height="16" rx="2.5" fill="#1A1917" />
    <rect x="125" y="22" width="5" height="16" rx="2.5" fill="#1A1917" />
    {[0, 1, 2].map((r) =>
      [0, 1, 2, 3, 4].map((c) => (
        <rect
          key={`${r}-${c}`}
          x={56 + c * 19}
          y={56 + r * 16}
          width="13"
          height="10"
          rx="3"
          fill={r === 1 && c === 3 ? '#E0EFEE' : '#F1ECE3'}
        />
      )),
    )}
    <circle cx="140" cy="88" r="15" fill="#0C6E6B" />
    <path
      d="M140 81a5 5 0 0 0-5 5v4l-1.5 2.5h13L145 90v-4a5 5 0 0 0-5-5zm-2 14a2 2 0 0 0 4 0z"
      fill="#fff"
    />
  </Frame>
)
