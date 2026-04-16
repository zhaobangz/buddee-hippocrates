/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        medical: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          950: '#042f2e',
        },
        brand: {
          cyan: '#22d3ee',
          teal: '#2dd4bf',
          indigo: '#6366f1',
          dark: '#0f172a',
          card: 'rgba(30, 41, 59, 0.7)',
        }
      },
      backgroundImage: {
        'glass-gradient': 'linear-gradient(135deg, rgba(20, 184, 166, 0.1), rgba(34, 211, 238, 0.1))',
        'mesh-gradient': 'radial-gradient(at 0% 0%, rgba(20, 184, 166, 0.15) 0, transparent 50%), radial-gradient(at 50% 0%, rgba(34, 211, 238, 0.15) 0, transparent 50%), radial-gradient(at 100% 0%, rgba(99, 102, 241, 0.15) 0, transparent 50%)',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 6s ease-in-out infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(45, 212, 191, 0.2), 0 0 10px rgba(45, 212, 191, 0.1)' },
          '100%': { boxShadow: '0 0 15px rgba(45, 212, 191, 0.6), 0 0 30px rgba(45, 212, 191, 0.3)' },
        }
      },
      backdropBlur: {
        xs: '2px',
      }
    },
  },
  plugins: [],
}
