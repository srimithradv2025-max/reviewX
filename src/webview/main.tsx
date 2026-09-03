import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/tailwind.css";

/**
 * Webview entry point
 * Builds the main React application for the VS Code ReviewX sidebar
 */

const container = document.getElementById("webview-container") as HTMLElement | null;
if (!container) {
  throw new Error("Webview container not found. Make sure index.html exists.");
}

// Render the main app
const root = ReactDOM.createRoot(container);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);