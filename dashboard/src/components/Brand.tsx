import { Link } from "react-router-dom";
import astrikos from "../assets/brand/astrikos.svg";
import dalmia from "../assets/brand/dalmia.svg";
import { brandLine, context, footer } from "../copy";

/**
 * The co-brand lockup: one capsule, two equal panels. The Astrikos artwork is light grey and needs a dark
 * ground; the Dalmia artwork is dark blue and multicolour and needs a white one. Putting each on its own
 * panel keeps both logos untouched (no recolouring) while reading as a single unit with equal weight.
 * Size steps with the viewport (32 → 36 → 40 → 44 px) so branding never dominates a small screen.
 */
export function BrandLockup() {
  return (
    <Link to="/" aria-label={`${brandLine.product}: Astrikos AI and Dalmia Bharat, home`} className="relative inline-flex shrink-0 rounded-[10px]">
      <span className="flex h-8 overflow-hidden rounded-[10px] ring-1 ring-sage/35 md:h-9 lg:h-10 xl:h-11 [&>span]:flex [&>span]:aspect-[2/1] [&>span]:items-center [&>span]:justify-center">
        <span className="bg-forest"><img src={astrikos} alt="Astrikos AI" width={89} height={84} className="h-[74%] w-auto" /></span>
        <span className="bg-white"><img src={dalmia} alt="Dalmia Bharat" width={606} height={292} className="h-[56%] w-auto" /></span>
      </span>
      {/* The seam: a small neutral chip, not an oversized ×. */}
      <span aria-hidden className="absolute left-1/2 top-1/2 grid h-4 w-4 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-brunswick font-mono text-[9px] leading-none text-mist ring-1 ring-sage/45">×</span>
    </Link>
  );
}

/**
 * The product name beside the lockup: not a navigation label but the product identity, and by a wide margin
 * the strongest text in the header (24 → 32 → 48 → 56 → 64 px by viewport; --header-h in index.css grows
 * with it). The steps are bounded by the bar itself: at each width the name, the lockup and the status block
 * must sit side by side without the name's nowrap running under them.
 * "Kiln" in Polar, "Intelligence" in Emerald, bold and tightly tracked, standing in the header's Emerald light.
 * A short Emerald rule and the plant caption sit under it, deliberately small so the name dominates them.
 * Hidden below 640 px, where the lockup and status already fill the bar and the page hero names the product.
 */
export function ProductLine() {
  const [first, ...rest] = brandLine.product.split(" ");
  return (
    <div className="hidden min-w-0 border-l border-sage/25 pl-4 sm:block lg:pl-6">
      <p className="glow-text whitespace-nowrap text-[24px] font-bold uppercase leading-[0.92] tracking-[-0.045em] text-polar md:text-[32px] lg:text-[48px] xl:text-[56px] 2xl:text-[64px]">
        {first} <span className="text-emerald">{rest.join(" ")}</span>
      </p>
      <div className="mt-2 flex items-center gap-2.5">
        <span aria-hidden className="h-px w-7 shrink-0 bg-rule lg:w-10" />
        <p className="truncate font-mono text-eyebrow uppercase text-sage">{context.plant}</p>
      </div>
    </div>
  );
}

/**
 * Abstract process-line motif for dark bands: concentric arcs (a kiln shell in section), horizontal
 * flow lines and node ticks. Low opacity, decorative only, never under body text.
 */
export const ProcessLines = ({ className = "" }: { className?: string }) => (
  <svg aria-hidden viewBox="0 0 640 300" preserveAspectRatio="xMaxYMid slice" fill="none" stroke="currentColor" strokeWidth="1"
    className={`pointer-events-none absolute inset-y-0 right-0 -z-10 h-full w-[min(70%,760px)] text-sage/25 ${className}`}>
    {[44, 80, 116, 152, 188].map((r, i) => <circle key={r} cx="470" cy="150" r={r} strokeOpacity={1 - i * 0.16} strokeDasharray={i === 2 ? "3 5" : undefined} />)}
    <path d="M0 150H282M658 150H640" strokeDasharray="2 6" />
    <path d="M120 70V230M200 40V260" strokeOpacity={0.6} />
    {[120, 200, 282].map((x) => <circle key={x} cx={x} cy="150" r="2.5" fill="currentColor" stroke="none" />)}
    <path d="M470 150 L618 76M470 150 L618 224" strokeOpacity={0.5} />
  </svg>
);

/** Restrained co-brand footer: text only, no repeated logos. */
export function BrandFooter() {
  return (
    <footer className="no-print on-dark border-t border-moss/60 bg-forest">
      <div className="mx-auto flex max-w-page flex-col gap-4 px-4 py-6 sm:px-8 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="font-mono text-eyebrow font-medium uppercase text-white">{footer.brands}</p>
          <p className="mt-2 text-label font-medium text-mist">{brandLine.product}</p>
          <p className="text-caption text-sage">{footer.scope}</p>
        </div>
        <p className="font-mono text-eyebrow uppercase text-sage md:text-right">{footer.status}</p>
      </div>
    </footer>
  );
}
