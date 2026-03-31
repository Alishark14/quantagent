/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          main: '#0f1117',
          card: '#1a1d26',
          elevated: '#252830',
        },
        border: {
          DEFAULT: '#2d3039',
        },
        profit: '#22c55e',
        loss: '#ef4444',
        accent: '#3b82f6',
        text: {
          primary: '#e5e7eb',
          secondary: '#9ca3af',
          muted: '#6b7280',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
