import { BrowserRouter as Router, Navigate, Route, Routes } from "react-router-dom";
import { MarketingChrome } from "./components/SiteNav";
import { DemoPage } from "./pages/Demo";
import { HomePage } from "./pages/Home";
import { HowItWorksPage } from "./pages/HowItWorks";
import { WorkspacePage } from "./pages/Workspace";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route
          path="/"
          element={
            <MarketingChrome>
              <HomePage />
            </MarketingChrome>
          }
        />
        <Route
          path="/how-it-works"
          element={
            <MarketingChrome>
              <HowItWorksPage />
            </MarketingChrome>
          }
        />
        <Route
          path="/demo"
          element={
            <MarketingChrome>
              <DemoPage />
            </MarketingChrome>
          }
        />
        <Route path="/app" element={<WorkspacePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}
