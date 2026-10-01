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
          bg: "#090a0f",
          card: "#12141c",
          surface: "#1a1d29",
          border: "#282c3f",
          accent: "#6366f1",
          hover: "#4f46e5",
          text: "#f3f4f6",
          muted: "#9ca3af",
        }
      }
    },
  },
  plugins: [],
}
