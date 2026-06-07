# Optional visualizations for full consilium

These are explanation artifacts, not proof. Use only when they clarify a high-stakes/full-mode run; do not make them mandatory for chat summaries.

## Useful views

1. Vote/repetition heatmap
   - rows = models
   - columns = claims
   - cells = support / not-addressed / verified-after-tool-check

2. Consensus matrix
   - model × model overlap score
   - useful for seeing redundant models or factions

3. Argument graph
   - nodes: question, options, claims, objections, evidence
   - edges: supports, contradicts, depends_on, evidenced_by

4. Evidence ledger
   - source
   - claims supported/opposed
   - reliability
   - caveats

## Libraries

- Static: Python `pandas`, `seaborn`, `matplotlib`, `networkx`.
- Web: React Flow / XYFlow, ECharts, Vega-Lite, TanStack Table.
- Markdown diagrams: Mermaid or Graphviz/DOT.
