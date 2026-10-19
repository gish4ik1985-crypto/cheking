import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import "./index.css"
import { ThemeProvider } from "@/lib/theme"
import { AuthProvider } from "@/lib/auth"
import { DialogsProvider } from "@/components/dialogs"
import App from "./App.tsx"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <DialogsProvider>
            <App />
          </DialogsProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>
)
