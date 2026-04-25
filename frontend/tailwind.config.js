/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bunq: {
          bg: '#050505',
          surface: '#111111',
          surface2: '#1A1A1A',
          border: 'rgba(255,255,255,0.06)',
          green: '#00C853',
          greenHover: '#00E676',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Inter', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 8px 30px rgba(0,0,0,0.35)',
        card: '0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 40px rgba(0,0,0,0.4)',
      },
      backgroundImage: {
        rainbow: 'linear-gradient(90deg, #FF3D8A 0%, #FF7A29 33%, #FFD23F 66%, #00C853 100%)',
      },
      borderRadius: {
        '2.5xl': '20px',
      },
      keyframes: {
        spin: { to: { transform: 'rotate(360deg)' } },
        fadeUp: {
          '0%': { opacity: 0, transform: 'translateY(8px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        spin: 'spin 700ms linear infinite',
        fadeUp: 'fadeUp 280ms cubic-bezier(.16,1,.3,1) both',
      },
    },
  },
  plugins: [],
}
