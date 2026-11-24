export default function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="26" height="26" fill="none">
          <path
            d="M16 2.8 27 7v8.2c0 6.4-4.4 11.7-11 14-6.6-2.3-11-7.6-11-14V7l11-4.2Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path
            d="M10.5 19.5c2.3-4.6 4.4-2.2 6.4-5.4 1.7-2.7 3.2-1.5 4.6-3.1"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
          <circle cx="21.4" cy="11" r="1.7" fill="currentColor" />
        </svg>
      </span>
      <span className="brand-text">
        <strong>SPOTTER</strong>
        <span>Route Safety</span>
      </span>
    </div>
  );
}
