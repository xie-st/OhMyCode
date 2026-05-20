/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular'],
      },
      colors: {
        // Override Tailwind's default pink ramp so every `pink-*` class in
        // the desktop matches the CLI accent (`ohmycode/_cli/output.py`
        // ACCENT = #ff6b9d). Shades 50-200 are blush tints; 500 is the
        // exact CLI hue; 600-900 step down in lightness toward raspberry.
        pink: {
          50:  '#fff5f8',
          100: '#ffe1ec',
          200: '#ffc4d6',
          300: '#ff9bbb',
          400: '#ff84ad',
          500: '#ff6b9d',
          600: '#ee4986',
          700: '#c8255f',
          800: '#9c1a4a',
          900: '#6e1235',
        },
      },
    },
  },
  plugins: [],
}
