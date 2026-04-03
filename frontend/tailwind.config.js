/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#FAFAF8',
        surface: '#FFFFFF',
        border: '#E8E5E0',
        accent: {
          DEFAULT: '#6B9E8A',
          light: '#E8F2ED',
          hover: '#5A8976'
        },
        text: {
          primary: '#2D3436',
          secondary: '#636E72'
        },
        status: {
          'on-track': {
            bg: '#E8F5E9',
            text: '#2E7D32'
          },
          behind: {
            bg: '#FFF8E1',
            text: '#F57F17'
          },
          'at-risk': {
            bg: '#FDE8E8',
            text: '#C62828'
          }
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
      }
    },
  },
  plugins: [],
}
