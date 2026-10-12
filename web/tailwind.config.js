/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        studio: {
          canvas: "#07080b",
          bg: "#0b0d13",
          panel: "#10121a",
          card: "#151822",
          surface: "#1c202e",
          border: "#23283a",
          borderLight: "#31374d",
          accent: "#6366f1",
          hover: "#4f46e5",
          text: "#f8fafc",
          muted: "#94a3b8",
          subtle: "#64748b",
        }
      }
    },
  },
  plugins: [],
}
