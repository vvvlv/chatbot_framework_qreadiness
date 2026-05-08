import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        navy: '#2F4156',
        teal: '#567C8D',
        skyblue: '#C8D9E6',
        beige: '#F5EFEB',
        'dark-beige': '#C7AE9D',
        'darker-beige': '#80604A',
        'light-teal': '#699FB7',
        background: 'var(--background)',
        foreground: 'var(--foreground)',
      },
      fontFamily: {
        title: ['"Playfair Display"', 'serif'],
        paragraph: ['Montserrat', 'sans-serif'],
      },
    },
  },
  plugins: [typography],
}
export default config
