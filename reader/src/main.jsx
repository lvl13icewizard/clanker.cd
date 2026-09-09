// The personal reader is a thin shell: the approved reader lives in
// site/reader and is shared with the public site's demo personas, so one
// layout serves both. This build reads /issues (the engine's output) as
// its owner's edition.
import React from "react";
import { createRoot } from "react-dom/client";
import App from "../../site/reader/App.jsx";
import "../../site/reader/styles.css";
createRoot(document.getElementById("root")).render(
  <App reader={{ name: "Andrew", since: 2015 }} />,
);
