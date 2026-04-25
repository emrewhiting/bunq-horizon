import { useEffect, useRef, useState } from 'react'
import { analyze, getContext, getPerspective, classifyImage } from './api'

const STAGES = { UPLOAD: 'upload', PRICE: 'price', RESULT: 'result' }

const FALLBACK_CTX = {
  goal: { name: 'Tokyo 2026', target_eur: 4500, current_eur: 1800, current_eta: '2026-08-04' },
  velocity: { daily_velocity_eur: 15 },
  baselines: {},
  categories: ['clothing', 'electronics', 'food_dining', 'groceries', 'transport', 'entertainment', 'beauty', 'home', 'other'],
}

const CAT_LABELS = {
  clothing: 'clothing', electronics: 'electronics', food_dining: 'food',
  groceries: 'groceries', transport: 'transport', entertainment: 'entertainment',
  beauty: 'beauty', home: 'home', other: 'other',
}

function CategoryIcon({ name, className = 'w-4 h-4' }) {
  // simple line glyphs per category — keeps the look clean, no emoji
  const stroke = 'currentColor'
  switch (name) {
    case 'clothing':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7 4l5 3 5-3 4 3-3 4-2-1v10H6V10L4 11 1 7z"/></svg>)
    case 'electronics':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="18" height="12" rx="2"/><path d="M2 21h20"/></svg>)
    case 'food_dining':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11h18M5 11v8h14v-8M7 7c2-3 8-3 10 0"/></svg>)
    case 'groceries':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 5h2l3 12h11l2-8H7"/><circle cx="9" cy="20" r="1.4"/><circle cx="17" cy="20" r="1.4"/></svg>)
    case 'transport':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 11h14M9 21l-1-2M15 21l1-2"/><circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/></svg>)
    case 'entertainment':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M10 9l5 3-5 3z" fill="currentColor"/></svg>)
    case 'beauty':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l3 6-3 12-3-12z"/></svg>)
    case 'home':
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11l9-7 9 7v9H3z"/><path d="M9 20v-6h6v6"/></svg>)
    default:
      return (<svg viewBox="0 0 24 24" className={className} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M6 7h12l-1 13H7zM9 7a3 3 0 016 0"/></svg>)
  }
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  } catch { return iso }
}

function formatPrice(p) {
  if (p == null) return ''
  return Number.isInteger(Number(p)) ? `€${p}` : `€${Number(p).toFixed(2)}`
}

export default function App() {
  const [stage, setStage] = useState(STAGES.UPLOAD)
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [vision, setVision] = useState(null)
  const [price, setPrice] = useState('')
  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [ctx, setCtx] = useState(FALLBACK_CTX)
  const [drag, setDrag] = useState(false)
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)

  useEffect(() => {
    let alive = true
    getContext()
      .then((c) => alive && setCtx({ ...FALLBACK_CTX, ...c }))
      .catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(null), 3200)
    return () => clearTimeout(t)
  }, [error])

  // Category always comes from the vision call. No manual override —
  // the whole point of the product is that the AI does the classification.
  const activeCategory = vision?.category || 'other'

  function handleFile(f) {
    if (!f) return
    if (!f.type.startsWith('image/')) { setError('please pick an image file'); return }
    setError(null)
    setFile(f)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(URL.createObjectURL(f))
    setStage(STAGES.PRICE)
    setLoading(true)
    classifyImage(f)
      .then(setVision)
      .catch(() => setVision({
        item: f.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' '),
        category: 'other', confidence: 'low', source: 'fallback',
      }))
      .finally(() => setLoading(false))
  }

  async function submitPrice() {
    const num = parseFloat(price)
    if (!num || num <= 0) { setError('enter a valid price'); return }
    setError(null)
    setLoading(true)
    try {
      let result
      if (file && !vision) {
        const r = await analyze({ file, price: num })
        setVision(r.vision)
        result = r.card
      } else {
        result = await getPerspective({
          price: num,
          category: activeCategory,
          item: vision?.item,
        })
      }
      setCard({ ...result, _price: num, _category: activeCategory })
      setStage(STAGES.RESULT)
    } catch (e) {
      console.warn('backend unreachable, using local fallback', e)
      setCard(localFallbackCard(num, activeCategory, vision?.item, ctx))
      setStage(STAGES.RESULT)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(null); setPreviewUrl(null); setVision(null)
    setPrice(''); setCard(null); setError(null); setStage(STAGES.UPLOAD)
  }

  return (
    <div className="min-h-screen w-full bg-bunq-bg flex justify-center pt-8 pb-16 px-4">
      <div className="w-full max-w-[400px] flex flex-col gap-5">
        <Header ctx={ctx} />

        {stage === STAGES.UPLOAD && (
          <UploadScreen
            drag={drag} setDrag={setDrag} onFile={handleFile}
            fileInputRef={fileInputRef} cameraInputRef={cameraInputRef}
          />
        )}

        {stage === STAGES.PRICE && (
          <PriceScreen
            previewUrl={previewUrl} vision={vision}
            activeCategory={activeCategory}
            price={price} setPrice={setPrice}
            onBack={reset} onSubmit={submitPrice} loading={loading}
          />
        )}

        {stage === STAGES.RESULT && card && (
          <ResultScreen
            card={card} vision={vision} previewUrl={previewUrl} onReset={reset}
          />
        )}
      </div>

      {error && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-rose-500/95 text-white text-sm px-4 py-2 rounded-xl shadow-soft z-50 animate-fadeUp">
          {error}
        </div>
      )}
    </div>
  )
}

function Header({ ctx }) {
  const goal = ctx.goal || {}
  const v = ctx.velocity?.daily_velocity_eur ?? 0
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-bunq-green shadow-[0_0_12px_#00C853]" />
          <span className="font-semibold tracking-tight text-[15px]">bunq Horizon</span>
        </div>
        <span className="text-white/40 text-xs tabular-nums">€{v.toFixed(2)}/day</span>
      </div>

      <div className="bg-bunq-surface rounded-2xl p-5 shadow-card relative">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-white/40">Saving for</div>
            <div className="mt-1 inline-block rainbow-underline font-bold text-[22px] leading-none tracking-tight">{goal.name || '—'}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-[11px] uppercase tracking-[0.14em] text-white/40">ETA</div>
            <div className="mt-1 font-semibold text-[15px] text-white/90">{formatDate(goal.current_eta)}</div>
          </div>
        </div>
        {goal.target_eur != null && (
          <div className="mt-4">
            <div className="h-[6px] bg-white/[0.06] rounded-full overflow-hidden">
              <div
                className="h-full bg-bunq-green rounded-full transition-[width] duration-700"
                style={{ width: `${Math.min(100, Math.max(2, ((goal.current_eur || 0) / goal.target_eur) * 100))}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-white/40 tabular-nums">
              <span>€{Math.round(goal.current_eur || 0)}</span>
              <span>€{Math.round(goal.target_eur)}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function UploadScreen({ drag, setDrag, onFile, fileInputRef, cameraInputRef }) {
  return (
    <div className="flex flex-col gap-5 animate-fadeUp">
      <div
        className={`relative rounded-2xl p-8 text-center transition-colors duration-150 ${
          drag ? 'bg-bunq-green/10 border-bunq-green/60' : 'bg-bunq-surface border-white/[0.06]'
        } border shadow-card`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f) }}
      >
        <div className="mx-auto mb-5 w-14 h-14 rounded-full bg-white/[0.04] flex items-center justify-center">
          <svg viewBox="0 0 24 24" className="w-7 h-7 text-white/70" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
            <circle cx="12" cy="13" r="3.5" />
          </svg>
        </div>
        <h2 className="text-[26px] font-bold tracking-tight leading-tight">
          See the cost <br /><span className="rainbow-underline inline-block">behind the price</span>
        </h2>
        <p className="mt-4 text-[14px] text-white/60 leading-relaxed">
          Snap any item. We'll show what it really costs your future self.
        </p>

        <div className="mt-6 flex flex-col gap-2">
          <button
            onClick={() => cameraInputRef.current?.click()}
            className="w-full rounded-2xl bg-bunq-green hover:bg-bunq-greenHover active:scale-[0.99] text-black font-semibold text-[15px] py-3.5 transition"
          >
            Take photo
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="w-full rounded-2xl bg-transparent text-white/80 font-medium text-[14px] py-3 border border-white/10 hover:bg-white/5 transition"
          >
            Upload from library
          </button>
        </div>

        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
        <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
      </div>

      <p className="text-center text-white/30 text-[11px] tracking-wide">
        you decide. we just give context.
      </p>
    </div>
  )
}

function PriceScreen({
  previewUrl, vision, activeCategory, price, setPrice, onBack, onSubmit, loading,
}) {
  const aiReady = !!vision
  return (
    <div className="flex flex-col gap-4 animate-fadeUp">
      <div className="relative rounded-2xl overflow-hidden bg-bunq-surface border border-white/[0.06] shadow-card">
        {previewUrl && <img src={previewUrl} alt="captured" className="w-full block max-h-[260px] object-cover" />}
        <div className="absolute top-3 left-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur border border-white/10 text-[12px] font-medium">
          {aiReady ? (
            <>
              <CategoryIcon name={vision.category} className="w-3.5 h-3.5 text-white/80" />
              <span className="text-white/90 capitalize truncate max-w-[220px]">{vision.item || 'item'}</span>
              {vision.source === 'fallback' && <span className="text-white/40">· no AI key</span>}
            </>
          ) : (
            <><Spinner size={12} /> <span className="text-white/70">identifying…</span></>
          )}
        </div>
      </div>

      <div className="bg-bunq-surface rounded-2xl p-5 border border-white/[0.06] shadow-card">
        <div className="text-[11px] uppercase tracking-[0.14em] text-white/40">How much</div>
        <div className="mt-2 flex items-center gap-2">
          <span className="text-3xl font-bold text-white/40">€</span>
          <input
            type="number" inputMode="decimal" placeholder="0"
            value={price} onChange={(e) => setPrice(e.target.value)} autoFocus
            className="flex-1 bg-transparent border-0 text-white text-4xl font-bold tracking-tight placeholder:text-white/20"
          />
        </div>

        <div className="mt-6 flex items-center gap-2 text-[12px] text-white/50">
          {aiReady ? (
            <>
              <CategoryIcon name={activeCategory} className="w-3.5 h-3.5 text-white/60" />
              <span>
                AI categorized this as{' '}
                <span className="text-white/90 capitalize font-medium">
                  {CAT_LABELS[activeCategory] || activeCategory}
                </span>
              </span>
            </>
          ) : (
            <><Spinner size={10} /> <span>AI is categorizing…</span></>
          )}
        </div>
      </div>

      <div className="flex gap-2 mt-1">
        <button
          onClick={onBack}
          className="rounded-2xl px-5 py-3.5 bg-transparent border border-white/10 text-white/80 text-[14px] font-medium hover:bg-white/5 transition"
        >
          Back
        </button>
        <button
          onClick={onSubmit} disabled={loading || !price}
          className="flex-1 rounded-2xl bg-bunq-green hover:bg-bunq-greenHover active:scale-[0.99] text-black font-semibold text-[15px] py-3.5 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? <><Spinner size={14} dark /> Calculating…</> : 'See impact'}
        </button>
      </div>
    </div>
  )
}

function ResultScreen({ card, vision, previewUrl, onReset }) {
  return (
    <div className="flex flex-col gap-4 animate-fadeUp">
      <div className="relative rounded-2xl overflow-hidden bg-bunq-surface border border-white/[0.06] shadow-card">
        {previewUrl && <img src={previewUrl} alt="item" className="w-full block max-h-[180px] object-cover opacity-90" />}
        <div className="absolute inset-0 bg-gradient-to-t from-bunq-bg via-transparent to-transparent" />
        <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur border border-white/10 text-[12px]">
            <CategoryIcon name={card._category} className="w-3.5 h-3.5 text-white/80" />
            <span className="text-white/90 capitalize">{vision?.item || card._category}</span>
          </div>
          <div className="text-white font-bold text-lg tabular-nums">{formatPrice(card._price)}</div>
        </div>
      </div>

      <div className="rainbow-border rounded-2xl bg-bunq-surface2 p-6 shadow-card">
        <div className="text-[11px] uppercase tracking-[0.14em] text-white/40">For context</div>
        <h3 className="mt-2 text-[22px] font-bold tracking-tight leading-tight">
          {card.headline}
        </h3>

        <div className="mt-5 flex flex-col gap-4">
          <Stat label="Goal impact" value={card.impact_line} accent="green" />
          <Stat label="Spending pace" value={card.context_line} />
          <Stat label="Carbon" value={card.carbon_line} />
        </div>

        <p className="mt-6 text-[12.5px] text-white/40">{card.footer || 'Your call.'}</p>
      </div>

      <div className="flex gap-2 mt-1">
        <button
          onClick={onReset}
          className="rounded-2xl px-5 py-3.5 bg-transparent border border-white/10 text-white/80 text-[14px] font-medium hover:bg-white/5 transition"
        >
          New item
        </button>
        <button
          onClick={onReset}
          className="flex-1 rounded-2xl bg-bunq-green hover:bg-bunq-greenHover active:scale-[0.99] text-black font-semibold text-[15px] py-3.5 transition"
        >
          Plan it · or skip
        </button>
      </div>
    </div>
  )
}

function Stat({ label, value, accent }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-[0.14em] text-white/40">{label}</span>
      <span className={`text-[15px] leading-snug ${accent === 'green' ? 'text-bunq-green' : 'text-white/90'}`}>
        {value || '—'}
      </span>
    </div>
  )
}

function Spinner({ size = 16, dark = false }) {
  return (
    <span
      className="inline-block rounded-full animate-spin"
      style={{
        width: size, height: size,
        border: `${Math.max(2, Math.round(size / 7))}px solid ${dark ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.18)'}`,
        borderTopColor: dark ? '#000' : '#00C853',
      }}
    />
  )
}

// Last-resort fallback if backend is fully unreachable. Mirrors the
// Perspective Card shape so the result screen renders the same way.
function localFallbackCard(price, category, item, ctx) {
  const v = ctx.velocity?.daily_velocity_eur || 15
  const baselines = ctx.baselines || {}
  const goal = ctx.goal || {}
  const factors = {
    clothing: 0.4, electronics: 0.55, food_dining: 0.18, groceries: 0.12,
    transport: 0.45, entertainment: 0.1, beauty: 0.25, home: 0.3, other: 0.2,
  }
  const f = factors[category] ?? factors.other
  const kg = +(price * f).toFixed(2)

  const days = v > 0 ? Math.round(price / v) : 0
  const newEta = goal.current_eta ? new Date(goal.current_eta) : new Date()
  newEta.setDate(newEta.getDate() + days)

  const baseline = baselines[category]
  const ratio = baseline ? price / baseline : null

  let pace = days === 0 ? 'same day at your pace'
           : days === 1 ? '~1 day at your pace'
                        : `~${days} days at your pace`
  if (ratio && (ratio >= 1.5 || ratio < 0.7)) pace += ` · ${ratio.toFixed(1)}x your usual ${category} spend`

  let eq
  if (kg <= 0) eq = 'negligible footprint'
  else if (kg < 5) eq = `≈ ${(kg / 3).toFixed(1)} beef burgers`
  else if (kg < 50) eq = `≈ ${Math.round(kg / 0.18)} km of driving`
  else {
    const yrs = kg / 21
    eq = yrs < 2 ? `≈ ${Math.round(yrs * 12)} months of a tree's offset`
                 : `≈ ${yrs.toFixed(1)} years of a mature tree's CO₂ offset`
  }

  const itemLabel = item || category
  const headline = `${itemLabel} — ${formatPrice(price)}`
  const impact = days === 0
    ? `No shift to ${goal.name || 'your goal'} — same day (${formatDate(goal.current_eta)})`
    : `Pushes ${goal.name || 'your goal'} from ${formatDate(goal.current_eta)} → ${formatDate(newEta.toISOString().slice(0,10))}`

  return {
    headline, impact_line: impact, context_line: pace,
    carbon_line: `${kg} kg CO₂e · ${eq}`,
    footer: 'Your call.',
    _price: price, _category: category,
  }
}
