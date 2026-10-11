"use client"

import * as React from "react"
import cytoscape from "cytoscape"
import type { GraphData } from "@/core/types"

interface Props {
  graph: GraphData
}

export function SubGraphRenderer({ graph }: Props) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const cyRef = React.useRef<cytoscape.Core | null>(null)
  const [tooltip, setTooltip] = React.useState<{
    text: string
    x: number
    y: number
  } | null>(null)

  React.useEffect(() => {
    if (!containerRef.current) return
    if (cyRef.current) {
      try { cyRef.current.destroy() } catch (_) { /* already destroyed */ }
      cyRef.current = null
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...graph.nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.label,
            color: n.color ?? "#93c5fd",
          },
        })),
        ...graph.edges.map((e) => ({
          data: {
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
            tooltip: e.tooltip,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "wrap",
            "text-max-width": "80px",
            color: "#1e293b",
            "font-size": "10px",
            width: 44,
            height: 44,
            "border-width": 1.5,
            "border-color": "#e2e8f0",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.2,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "9px",
            color: "#64748b",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 80,
        gravity: 0.3,
        numIter: 1000,
      },
    })

    // Tooltip events
    cy.on("mouseover", "edge", (evt) => {
      const edge = evt.target
      const tip = edge.data("tooltip")
      if (tip) {
        setTooltip({
          text: tip,
          x: evt.renderedPosition.x,
          y: evt.renderedPosition.y - 10,
        })
      }
    })
    cy.on("mouseout", "edge", () => {
      setTooltip(null)
    })

    cyRef.current = cy
    const timer = setTimeout(() => {
      try {
        if (!cy.destroyed()) cy.fit(undefined, 30)
      } catch (_) { /* ignore */ }
    }, 600)

    return () => {
      clearTimeout(timer)
      try { cy.destroy() } catch (_) { /* ignore */ }
      cyRef.current = null
    }
  }, [graph])

  return (
    <div className="relative min-h-[320px] w-full rounded-md border bg-white">
      <div ref={containerRef} className="h-[320px] w-full" />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-50 max-w-xs rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs leading-relaxed text-popover-foreground shadow-md"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          {tooltip.text.split("\n").map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}
