/** @type {import('tailwindcss').Config} */
// Modernist design system, inverted for a dark ground (design_handoff_poker_flow).
// Flat, architectural, Archivo throughout, zero corner radius, 2px rules, one
// red accent. Tokens here so screens never sprinkle arbitrary hex.
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ground: '#201e1d',
        surface: '#2d2b2b',
        'surface-deep': '#444141',
        ink: '#f3f2f2',
        'ink-muted': '#9b9797',
        'ink-dim': '#605d5d',
        accent: '#ff563c',
        'accent-light': '#ff9783',
        'accent-deep': '#ae1800',
        'accent-tint': '#471d16',
        'card-red': '#ec3013',
      },
      fontFamily: {
        sans: ['Archivo', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderColor: {
        'divider-strong': 'rgba(243,242,242,.35)',
        'divider-mid': 'rgba(243,242,242,.2)',
        'divider-light': 'rgba(243,242,242,.12)',
      },
      borderRadius: {
        none: '0',
        DEFAULT: '0',
        md: '0',
        lg: '0',
        xl: '0',
        full: '9999px', // kept for the rare pill (badges use square by default)
      },
      letterSpacing: {
        label: '.14em',
        seat: '.1em',
        btn: '.07em',
        brand: '.12em',
      },
    },
  },
  plugins: [],
}
