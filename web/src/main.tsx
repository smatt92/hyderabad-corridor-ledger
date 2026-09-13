import { render } from "preact";
import "uplot/dist/uPlot.min.css";
import { AnalystApp } from "./analyst/AnalystApp";
import "./styles.css";
import { WallApp } from "./wall/WallApp";

// One bundle, two separate layout trees. Switching mode is a full navigation,
// so nothing from one tree survives into the other.
const mode = new URLSearchParams(location.search).get("mode");
const root = document.getElementById("app");
if (root) render(mode === "wall" ? <WallApp /> : <AnalystApp />, root);
