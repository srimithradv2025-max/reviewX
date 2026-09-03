import type { Config } from "tailwindcss";
import { resolve } from "path";

const webviewRoot = resolve(__dirname, "src", "webview");

export default {
  content: [
    resolve(webviewRoot, "index.html"),
    resolve(webviewRoot, "**/*.{js,ts,jsx,tsx}")
  ],
  theme: {
    extend: {
      colors: {
        "vscode-editor-background": "var(--vscode-editor-background)",
        "vscode-editor-foreground": "var(--vscode-editor-foreground)",
        "vscode-editorLineNumber-foreground": "var(--vscode-editorLineNumber-foreground)",
        "vscode-editorLineNumber-activeForeground": "var(--vscode-editorLineNumber-activeForeground)",
        "vscode-editorCursor-foreground": "var(--vscode-editorCursor-foreground)",
        "vscode-sideBar-background": "var(--vscode-sideBar-background)",
        "vscode-sideBar-foreground": "var(--vscode-sideBar-foreground)",
        "vscode-activityBar-background": "var(--vscode-activityBar-background)",
        "vscode-activityBar-foreground": "var(--vscode-activityBar-foreground)",
        "vscode-activityBarBadge-background": "var(--vscode-activityBarBadge-background)",
        "vscode-input-background": "var(--vscode-input-background)",
        "vscode-input-foreground": "var(--vscode-input-foreground)",
        "vscode-input-border": "var(--vscode-input-border)",
        "vscode-input-placeholderForeground": "var(--vscode-input-placeholderForeground)",
        "vscode-button-background": "var(--vscode-button-background)",
        "vscode-button-foreground": "var(--vscode-button-foreground)",
        "vscode-button-secondaryBackground": "var(--vscode-button-secondaryBackground)",
        "vscode-button-hoverBackground": "var(--vscode-button-hoverBackground)",
        "vscode-dropdown-background": "var(--vscode-dropdown-background)",
        "vscode-dropdown-border": "var(--vscode-dropdown-border)",
        "vscode-list-activeSelectionBackground": "var(--vscode-list-activeSelectionBackground)",
        "vscode-list-hoverBackground": "var(--vscode-list-hoverBackground)",
        "vscode-notificationBackground": "var(--vscode-notificationBackground)",
        "vscode-dialog-background": "var(--vscode-dialog-background)",
        "vscode-badge-background": "var(--vscode-badge-background)",
        "vscode-progressBar-background": "var(--vscode-progressBar-background)",
        "vscode-diffEditor-insertedTextBackground": "var(--vscode-diffEditor-insertedTextBackground)",
        "vscode-diffEditor-removedTextBackground": "var(--vscode-diffEditor-removedTextBackground)",
        "vscode-problemsErrorIcon-foreground": "var(--vscode-problemsErrorIcon-foreground)",
        "vscode-problemsWarningIcon-foreground": "var(--vscode-problemsWarningIcon-foreground)",
        "vscode-problemsInfoIcon-foreground": "var(--vscode-problemsInfoIcon-foreground)",
        "vscode-editorGutter-addedBackground": "var(--vscode-editorGutter-addedBackground)",
        "vscode-editorGutter-modifiedBackground": "var(--vscode-editorGutter-modifiedBackground)"
      },
      fontFamily: {
        mono: ["var(--vscode-editor-font-family)", "Consolas", "monospace"],
        ui: ["var(--vscode-ui-font-family)", "Segoe UI", "sans-serif"]
      },
      fontSize: {
        "vscode-small": "var(--vscode-font-size)"
      },
      borderRadius: {
        "vscode": "var(--vscode-widget-borderRadius, 2px)"
      },
      boxShadow: {
        "vscode-dropdown": "0 2px 8px var(--vscode-widget-shadow)",
        "vscode-panel": "0 2px 8px var(--vscode-widget-shadow)"
      }
    }
  },
  plugins: []
} satisfies Config;