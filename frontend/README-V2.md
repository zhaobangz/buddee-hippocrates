# Buddi Clinical Portal Redesign (v2)

This directory contains the modernized, production-quality frontend for the Buddi Clinical Agent System.

## ✨ Key Features
- **Glassmorphic UI**: High-end medical aesthetic with blurred panels and mesh gradients.
- **Clinical Chat**: Streaming AI responses with clinical citations and executable actions.
- **Shadow Mode**: Real-time comparison between AI recommendations and expert baselines.
- **Risk Dashboard**: Visual heatmap of patient focus areas and intelligence-driven care plans.
- **Perception Widget**: Multi-modal input simulation (Voice/OCR).

## 🛠 Tech Stack
- **Frontend**: React 18, Vite, TailwindCSS
- **Animations**: Framer Motion
- **Icons**: Lucide React
- **State Management**: Zustand
- **Routing**: React Router 6

## 🚀 Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Run Local Development Server
```bash
npm run dev
```

### 3. Build for Production
```bash
npm run build
```

## 🏗 Architecture Decisions
1. **Zustand for State**: Lightweight and fast, perfect for high-frequency clinical data updates without the boilerplate of Redux.
2. **Tailwind Design System**: Custom tokens for `medical` and `brand` colors ensure consistency across the glass panels.
3. **Component-Based Shell**: The `Layout` component provides a rigid clinical structure (sidebar/topbar) while allowing dynamic workspace flexibility.
4. **Safety-First UI**: Includes persistent disclaimers and human-in-the-loop confirmation patterns for high-risk actions.

---
*Disclaimer: This is a Clinical Decision Support (CDS) tool mockup. It is not intended for direct diagnosis or medical treatment.*
