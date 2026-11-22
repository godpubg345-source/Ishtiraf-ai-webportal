// IshtirafAI portal design system: Tailwind maps every legacy colour name onto
// the theme ramps in static/css/src/app.css, so light/dark flips with data-theme.
// Build (no Node project needed):
//   npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/src/app.css -o static/css/app.css --minify
const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900];
const ramp = (name) => Object.fromEntries(
  STEPS.map((s) => [s, `rgb(var(--${name}-${s}) / <alpha-value>)`]).concat([[950, `rgb(var(--${name}-900) / <alpha-value>)`]]));
const g = ramp('g'), brand = ramp('brand'), refer = ramp('refer'), unsure = ramp('unsure'),
  clear = ramp('clear'), violet = ramp('violet');

module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  // Built from data in templates (status--{{ k }}, tone-{{ k }}), so Tailwind cannot see them.
  safelist: [{ pattern: /^(status--|tone-)(refer|unsure|clear|none|brand)$/ }],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    colors: {
      transparent: 'transparent', current: 'currentColor', inherit: 'inherit',
      black: '#000', white: 'rgb(var(--surface) / <alpha-value>)', surface: 'rgb(var(--surface) / <alpha-value>)',
      gray: g, slate: g, zinc: g, neutral: g, stone: g,
      brand, blue: brand, cyan: brand, sky: brand, teal: brand, indigo: brand,
      violet, purple: violet, fuchsia: violet, pink: violet,
      refer, red: refer, rose: refer,
      unsure, orange: unsure, amber: unsure, yellow: unsure,
      clear, green: clear, emerald: clear, lime: clear,
    },
    extend: {
      fontFamily: {
        sans: ['"Instrument Sans"', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        display: ['"Instrument Serif"', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'Consolas', 'monospace'],
      },
      borderRadius: { xl: '14px', '2xl': '18px', '3xl': '24px' },
    },
  },
};
