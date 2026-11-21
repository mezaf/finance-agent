import React from "react";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { Doughnut } from "react-chartjs-2";

ChartJS.register(ArcElement, Tooltip, Legend);

function flattenSunburst(node, depth = 0, parent = "") {
  if (!node) return [];
  const name = parent ? `${parent} / ${node.name}` : node.name;

  if (!node.children || node.children.length === 0) {
    return [{ name, value: node.value || 0 }];
  }

  return node.children.flatMap((child) => flattenSunburst(child, depth + 1, name));
}

export default function AnalysisChart({ data, onDrill }) {
  if (!data || !data.children || data.children.length === 0) {
    return <div className="chart-empty">No analysis data available.</div>;
  }

  // drilldown state: path is array of names representing the current node path
  const [path, setPath] = React.useState([]);

  // navigate into a child
  const drillInto = (name) => {
    const next = [...path, name];
    setPath(next);
    if (onDrill) onDrill(next);
  };
  const drillUp = () => setPath((p) => p.slice(0, -1));

  // locate current node by path
  const locate = (node, remainingPath) => {
    if (!remainingPath || remainingPath.length === 0) return node;
    const [next, ...rest] = remainingPath;
    const child = (node.children || []).find((c) => c.name === next);
    if (!child) return null;
    return locate(child, rest);
  };

  const current = locate(data, path) || data;
  const flattened = flattenSunburst(current).filter((item) => item.value > 0);
  const labels = flattened.map((item) => item.name);
  const values = flattened.map((item) => item.value);

  return (
    <div className="analysis-chart">
      <h2>Analysis Breakdown</h2>
      <div className="drill-controls">
        <div className="drill-path">Path: {path.length ? path.join(' / ') : 'root'}</div>
        {path.length > 0 && (
          <button onClick={drillUp} className="small-button">Back</button>
        )}
      </div>
      <Doughnut
        data={{ labels, datasets: [{ data: values, backgroundColor: labels.map((_, i) => [`#3B82F6`, `#10B981`, `#EF4444`, `#8B5CF6`, `#F59E0B`, `#A0AEC0`][i % 6]) }] }}
      />
      <div className="drill-children">
        {(current.children || []).map((c) => (
          <button key={c.name} className="drill-button" onClick={() => drillInto(c.name)}>{c.name}</button>
        ))}
      </div>
    </div>
  );
}
