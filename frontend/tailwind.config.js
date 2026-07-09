/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        clinical: {
          // Light theme tokens
          bg: '#F6F7F5',
          surface: '#FFFFFF',
          border: '#E3E7E4',
          fill: '#EEF1EF',
          ink: '#15302D',
          secondary: '#4A625E',
          muted: '#6E827F',
          // Primary action
          primary: '#0F766E',
          'primary-hover': '#115E59',
          // Status (on white)
          positive: '#047857',
          'positive-bg': '#ECFDF3',
          caution: '#B45309',
          'caution-bg': '#FEF3E2',
          risk: '#BE123C',
          'risk-bg': '#FDECEF',
          info: '#1D4ED8',
          'info-bg': '#EFF6FF',
        },
      },
      borderRadius: {
        card: '8px',
        control: '6px',
      },
      spacing: {
        '4.5': '1.125rem',
      },
      maxWidth: {
        'content': '1200px',
      },
      boxShadow: {
        'card': '0 1px 2px rgba(21,48,45,0.06)',
        'card-dark': '0 1px 2px rgba(0,0,0,0.2)',
        'dropdown': '0 4px 12px rgba(21,48,45,0.12)',
        'dropdown-dark': '0 4px 12px rgba(0,0,0,0.35)',
      },
      transitionDuration: {
        '150': '150ms',
        '200': '200ms',
      },
      transitionTimingFunction: {
        'out': 'ease-out',
      },
    },
  },
  plugins: [],
}
