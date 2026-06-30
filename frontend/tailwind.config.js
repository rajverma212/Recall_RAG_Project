/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Ember warm-dark backgrounds (mapped onto the existing scale names
        // so pre-existing classes pick up the new palette automatically)
        surface: {
          50: '#1a1714',  // border (faint) — inner rows
          100: '#1e1b15', // border (subtle) — default borders
          200: '#252119', // border (muted) — card borders
          800: '#181510', // surface — cards, inputs
          850: '#13110e', // raised — nested cards
          900: '#100f0d', // base — page bg
          950: '#0b0a08', // deepest — sidebar bg
        },
        // Accent: Ember amber
        accent: {
          300: '#f0a877',
          400: '#e8894a', // hover
          500: '#d97a3a', // primary action, active nav, donuts
          600: '#c4692e',
          700: '#a85724',
        },
        // Warm grays — override Tailwind's cool `slate` so existing text
        // classes (slate-100/300/400/600...) render in the Ember warm scale
        slate: {
          100: '#ede8df', // text primary — headings, values
          200: '#d8d0c2',
          300: '#c0b8a8', // body answer text
          400: '#9b9280', // text secondary — subtitles, meta
          500: '#7d7464',
          600: '#66625a', // text muted — inactive nav
          700: '#252119', // borders
          800: '#1e1b15',
          900: '#100f0d',
          950: '#0b0a08',
        },
        // Status (Ember tints)
        success: {
          400: '#6dd49a',
          500: '#6dd49a',
          900: '#14352a',
        },
        warning: {
          400: '#e8be52',
          500: '#e8be52',
          900: '#3a2f12',
        },
        danger: {
          400: '#d96060',
          500: '#d96060',
          900: '#3a1818',
        },
      },
      fontFamily: {
        sans: ['Space Grotesk', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Instrument Serif', 'ui-serif', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      letterSpacing: {
        label: '0.14em',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-dot': 'pulseDot 2s ease-in-out infinite',
        'bar-grow': 'barGrow 0.8s ease-out forwards',
        blink: 'blink 1.05s step-end infinite',
        shimmer: 'shimmer 4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseDot: {
          '0%,100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '.38', transform: 'scale(.7)' },
        },
        barGrow: {
          from: { transform: 'scaleX(0)' },
          to: { transform: 'scaleX(1)' },
        },
        blink: {
          '0%,49%': { opacity: '1' },
          '50%,100%': { opacity: '0' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(320%)' },
        },
      },
    },
  },
  plugins: [],
}
